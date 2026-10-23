#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline key-accuracy validation: ../.conda-music/python.exe validate.py"""
import argparse
import json
import os
import platform
import tempfile
import time
from importlib.metadata import version
from pathlib import Path

# Numba's default cache is inside the read-only conda installation in this sandbox.
os.environ.setdefault("NUMBA_CACHE_DIR", str(Path(tempfile.gettempdir()) / "music_scribe_numba_cache"))

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import fftconvolve
from selftest import SR, analyse, make_piece
from music_scribe import PC_NAMES

CASES = [(7, "major"), (2, "minor"), (0, "major"), (9, "minor"),
         (5, "major"), (11, "minor"), (4, "minor"), (10, "major")]
CONDITIONS = ["clean", "reverb", "noise_20", "noise_10", "noise_5",
              "8khz", "tempo_0.95", "tempo_1.05"]
LABELS = {"clean": "Clean baseline", "reverb": "Reverb, RT60 0.60 s, wet gain 0.35",
          "noise_20": "White noise, SNR 20 dB", "noise_10": "White noise, SNR 10 dB",
          "noise_5": "White noise, SNR 5 dB", "8khz": "Downsample to 8 kHz",
          "tempo_0.95": "Tempo -5%, pitch preserved", "tempo_1.05": "Tempo +5%, pitch preserved"}


def degrade(y, condition, seed):
    rng = np.random.default_rng(seed)
    metadata = {}
    sr = SR
    if condition == "clean":
        out = y.copy()
    elif condition == "reverb":
        t = np.arange(int(0.6 * SR)) / SR
        ir = rng.normal(size=len(t)) * np.exp(-np.log(1000) * t / 0.6)
        ir /= np.linalg.norm(ir)
        ir *= 0.35
        ir[0] += 1.0
        out = fftconvolve(y, ir, mode="full")
    elif condition.startswith("noise_"):
        snr = float(condition.split("_")[1])
        noise = rng.normal(size=len(y))
        noise *= np.sqrt(np.mean(y ** 2) / np.mean(noise ** 2)) * 10 ** (-snr / 20)
        metadata["measured_snr_db"] = float(10 * np.log10(np.mean(y ** 2) / np.mean(noise ** 2)))
        assert abs(metadata["measured_snr_db"] - snr) < 1e-6
        out = y + noise
    elif condition == "8khz":
        sr = 8000
        out = librosa.resample(y, orig_sr=SR, target_sr=sr)
    elif condition.startswith("tempo_"):
        rate = float(condition.split("_")[1])
        out = librosa.effects.time_stretch(y, rate=rate)
        metadata["rate"] = rate
        assert abs(len(out) - round(len(y) / rate)) <= 1
    else:
        raise ValueError(condition)
    # A common peak gain prevents PCM clipping and does not alter the SNR.
    out = out * min(1.0, 0.99 / max(float(np.max(np.abs(out))), 1e-12))
    assert np.all(np.isfinite(out))
    return out.astype(np.float32), sr, metadata


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path(__file__).with_name("VALIDATION.md"))
    args = ap.parse_args()
    started = time.perf_counter()
    results = []
    with tempfile.TemporaryDirectory(prefix="music_scribe_validation_") as tmp:
        for pc, mode in CASES:
            seed = pc * 13 + len(mode)
            np.random.seed(seed)
            clean = make_piece(pc, mode)
            for condition in CONDITIONS:
                y, sr, metadata = degrade(clean, condition, seed + 1000)
                fp = Path(tmp) / f"{pc}_{mode}_{condition}.wav"
                # Match selftest's PCM16 file encoding for the clean control.
                sf.write(str(fp), y, sr, subtype="PCM_16")
                row = {"target": [pc, mode], "condition": condition, "sample_rate": sr, **metadata}
                try:
                    best, share, _ = analyse(fp)
                    row.update(prediction=list(best), correct=best == (pc, mode), score_share=float(share))
                    label = f"{PC_NAMES[best[0]]} {best[1]}"
                except Exception as exc:
                    row.update(prediction=None, correct=False, error=f"{type(exc).__name__}: {exc}")
                    label = row["error"]
                results.append(row)
                print(f"{len(results):02d}/64 {condition}: {PC_NAMES[pc]} {mode} -> {label} "
                      f"{'PASS' if row['correct'] else 'FAIL'}", flush=True)
    clean_hits = sum(r["correct"] for r in results if r["condition"] == "clean")
    lines = ["# Offline degradation validation", "",
             "Run from the project directory (no downloads or package changes):", "",
             "```powershell", "# Use the compatible environment described in README.md", "python validate.py", "```", "",
             "Eight existing seeded synthetic pieces; each condition is applied independently to the same clean audio. "
             "Every file is transcribed again with Basic Pitch, and tempo, chroma, and bar-window key fusion are recomputed. "
             "No ground-truth notes or tempo are supplied to analysis. Exact tonic AND mode must match. "
             "Errors count as incorrect and remain in the denominator.", "",
             "| Degradation | Correct / total | Key accuracy | Change vs clean | Errors |",
             "|---|---:|---:|---:|---:|"]
    for condition in CONDITIONS:
        rows = [r for r in results if r["condition"] == condition]
        hits = sum(r["correct"] for r in rows)
        errors = sum("error" in r for r in rows)
        lines.append(f"| {LABELS[condition]} | {hits}/8 | {hits/8:.1%} | {(hits-clean_hits)/8*100:+.1f} pp | {errors} |")
    lines += ["", "Failed cases (including errors):", ""]
    failures = [r for r in results if not r["correct"]]
    if not failures:
        lines.append("None.")
    for row in failures:
        pc, mode = row["target"]
        pred = row["prediction"]
        actual = f"{PC_NAMES[pred[0]]} {pred[1]}" if pred else row["error"]
        lines.append(f"- {LABELS[row['condition']]}: expected {PC_NAMES[pc]} {mode}; got {actual}.")
    lines += ["", "Protocol and limits:", "",
              "- Original cases: G major, D minor, C major, A minor, F major, B minor, E minor, A# major. "
              "Seed = tonic_pc * 13 + len(mode); five bars at synthesis BPM 100 plus one second tail; PCM16 WAV.",
              "- Reverb: causal FFT convolution (scipy.signal.fftconvolve), seeded diffuse impulse response with "
              "0.60-second exponential RT60 envelope, unit wet L2 norm scaled to 0.35, direct impulse gain 1; full tail retained.",
              "- Noise: independent seeded white Gaussian noise, scaled by measured RMS to 20/10/5 dB SNR "
              "before a common anti-clipping gain. SNR is verified before PCM16 quantization.",
              "- 8 kHz audio is actually written at 8000 Hz; the existing analysis resamples it to 22050 Hz. "
              "Tempo changes use librosa.effects.time_stretch at 0.95/1.05, retaining pitch; each is a separate condition.",
              "- These are eight related synthetic pieces with controlled degradations, not a real-music dataset. "
              "Each miss changes the row by 12.5 percentage points; rows are paired and not independent samples. "
              "This table does not establish real-mix accuracy, calibration, or transcription/score quality.", "",
              f"Python {platform.python_version()}; " + "; ".join(f"{p} {version(p)}" for p in
                  ("basic-pitch", "librosa", "numpy", "scipy", "onnxruntime")) + ".",
              f"Measured wall time: {time.perf_counter()-started:.1f} seconds.", "",
              "Per-case machine-readable observations: `" + args.out.with_suffix(".json").name + "`."]
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    args.out.with_suffix(".json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}; clean {clean_hits}/8; errors {sum('error' in r for r in results)}", flush=True)
    return 1 if any("error" in r for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
