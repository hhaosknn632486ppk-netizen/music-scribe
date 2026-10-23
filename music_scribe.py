#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
music_scribe.py — 音频 -> 调性分析 + 五线谱（可复用工具，非一次性脚本）

流程
  1. 神经转录：Spotify Basic Pitch (ICASSP 2022)，多音（和弦）音符事件
  2. 定调：四种分析视角（其中三种共用转录结果）× 两套音级轮廓
       证据 A 音符直方图（时长×力度加权）
       证据 B 低音骨架（每个同时发声点取最低音，权重加成）
       证据 C 音频 HPCP/CQT 色度（不依赖转录，直接看谱能量）
       轮廓 Krumhansl-Kessler + Temperley，取 24 调排名与相对置信度
  3. 分段定调：滑窗 12s / hop 3s -> 转调时间轴
  4. 记谱：music21 量化到 16 分音符 -> MusicXML -> Verovio 排版 -> SVG
  5. 报告：单页 HTML（结论 / 排名 / 时间轴 / 密度 / 谱面 / 边界说明）

用法
  python music_scribe.py input.mp3 -o out_dir
  python music_scribe.py input.mp3 -o out_dir --mode full --bpm 92 --ts 3/4
  python music_scribe.py song.mp3 -o out_dir --separate --stems other,bass   # 密集混音
"""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib.metadata
import json
import math
import os
from functools import lru_cache
import subprocess
import sys
import time
import warnings
from pathlib import Path

if '--semantics' in sys.argv or '--semantics-only' in sys.argv:
    os.environ.setdefault('OPENBLAS_NUM_THREADS', '2')
    os.environ.setdefault('OMP_NUM_THREADS', '2')

import numpy as np

VERSION = "1.3.1"
SCHEMA_VERSION = "music-scribe/1.1"
TRANSCRIPTION_PARAMETERS = dict(onset_threshold=0.5, frame_threshold=0.3,
    minimum_note_length=90.0, minimum_frequency=27.5, maximum_frequency=4200.0,
    multiple_pitch_bends=False, melodia_trick=True, midi_tempo=120)
SOURCE_NAMES = ("音符", "低音", "色度", "和弦")

PC_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
KEY_SPELLINGS = {
    "major": ("C", "D-", "D", "E-", "E", "F", "F#", "G", "A-", "A", "B-", "B"),
    "minor": ("C", "C#", "D", "E-", "E", "F", "F#", "G", "G#", "A", "B-", "B"),
}


def key_label(k):
    if k is None:
        return "证据不足"
    spelling = KEY_SPELLINGS[k[1]][k[0]].replace("-", "♭").replace("#", "♯")
    return f'{spelling} {"大调" if k[1] == "major" else "小调"}'


def key_record(k):
    return None if k is None else {"tonic_pc": int(k[0]), "mode": k[1], "label": key_label(k)}


def bar_seconds(bpm, ts):
    """BPM is always quarter notes/minute, including compound and cut time."""
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError("BPM 必须为有限正数；单位为四分音符/分钟")
    return ts[0] * 4.0 / ts[1] * 60.0 / bpm


def bar_spans(duration, bpm, ts, origin=0.0):
    width = bar_seconds(bpm, ts)
    spans = [(0.0, min(origin, duration))] if origin > 0 else []
    index = 0
    while origin + index * width < duration:
        start = origin + index * width
        spans.append((start, min(duration, start + width)))
        index += 1
    return spans


def has_scores(tab):
    values = np.asarray(list(tab.values()), dtype=float)
    return bool(values.size and np.isfinite(values).all() and np.ptp(values) > 1e-9)


def select_key(fused, tables):
    """Historical three-vote safeguard, excluding unavailable/flat score paths."""
    solo = {name: max(tab, key=tab.get) if has_scores(tab) else None
            for name, tab in tables.items()}
    votes = {}
    for candidate in solo.values():
        if candidate is not None:
            votes[candidate] = votes.get(candidate, 0) + 1
    best = max(fused, key=fused.get) if votes and has_scores(fused) else None
    candidate, count = max(votes.items(), key=lambda x: x[1]) if votes else (None, 0)
    consensus = {"agree": count, "available": sum(k is not None for k in solo.values()),
                 "majority": key_label(candidate) if count >= 3 else None,
                 "votes": {key_label(k): n for k, n in sorted(votes.items(), key=lambda x: -x[1])},
                 "corrected": False, "pre_correction": key_record(best),
                 "independent_confirmations": False,
                 "dependency_note": "音符、低音、和弦共用 Basic Pitch 转录；一致票数不是独立确认次数。"}
    if best is not None and count >= 3 and key_conflict(best, candidate):
        consensus.update(corrected=True, was=key_label(best))
        best = candidate
    return best, solo, consensus

KK_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
KK_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
TP_MAJOR = [5.0, 2.0, 3.5, 2.0, 4.5, 4.0, 2.0, 4.5, 2.0, 3.5, 1.5, 4.0]
TP_MINOR = [5.0, 2.0, 3.5, 4.5, 2.0, 4.0, 2.0, 4.5, 3.5, 2.0, 1.5, 4.0]
PROFILES = {
    "major": [np.array(KK_MAJOR), np.array(TP_MAJOR)],
    "minor": [np.array(KK_MINOR), np.array(TP_MINOR)],
}


# ----------------------------------------------------------------------------- 基础
def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    den = np.linalg.norm(a) * np.linalg.norm(b)
    return float(a.dot(b) / den) if den else 0.0


def key_table(dist: np.ndarray) -> dict:
    """dist: 12 维音级权重 -> {(tonic_pc, mode): 相关系数}"""
    dist = np.asarray(dist, dtype=float)
    if dist.sum() <= 0:
        return {(t, m): 0.0 for t in range(12) for m in ("major", "minor")}
    out = {}
    for t in range(12):
        rot = np.roll(dist, -t)
        for mode, profs in PROFILES.items():
            out[(t, mode)] = float(np.mean([_pearson(rot, p) for p in profs]))
    return out


def z24(d: dict) -> dict:
    v = np.array(list(d.values()), dtype=float)
    sd = v.std()
    if sd < 1e-9:
        return {k: 0.0 for k in d}
    m = v.mean()
    return {k: (d[k] - m) / sd for k in d}


def key_fifths(k) -> int:
    """调号圈位置（0-11）。关系大小调得到同一个值：C 大调与 A 小调都是 0。"""
    t, m = k
    return ((t + (3 if m == "minor" else 0)) * 7) % 12


def key_conflict(a, b) -> bool:
    """两个调是否「真的」冲突。

    同主音（C 大调 vs C 小调）、同调号（C 大调 vs A 小调）都算同一调域，不算冲突。
    这一条很关键：关系大小调的分辨恰恰只能靠和弦的终止式，
    若把「三路说 C 大调、和弦说 A 小调」当成冲突去多数决，
    等于把唯一能分开平行大小调的证据掐掉。
    """
    return a != b and a[0] != b[0] and key_fifths(a) != key_fifths(b)


def fuse(dist_note, dist_bass, dist_chroma, func=None, w=(0.30, 0.18, 0.15, 0.37)) -> dict:
    parts, ws = [], []
    tables = [key_table(dist_note), key_table(dist_bass),
              key_table(dist_chroma) if dist_chroma is not None else {}, func or {}]
    for tab, weight in zip(tables, w):
        if weight > 0 and has_scores(tab):
            parts.append(z24(tab)); ws.append(weight)
    if not parts:
        return key_table(np.zeros(12))
    tot = sum(ws)
    out = {}
    for k in parts[0]:
        out[k] = sum(p[k] * (wt / tot) for p, wt in zip(parts, ws))
    return out


# ------------------------------------------------------------------- 和弦功能（第四路）
CHORD_SHAPES = {"": [0, 4, 7], "m": [0, 3, 7], "dim": [0, 3, 6], "aug": [0, 4, 8],
                "maj7": [0, 4, 7, 11], "m7": [0, 3, 7, 10],
                "7": [0, 4, 7, 10], "m7b5": [0, 3, 6, 10]}
SCALES = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10]}
DEGREE_Q = {"major": ["", "m", "m", "", "", "m", "dim"],
            "minor": ["m", "dim", "", "m", "m", "", ""]}


def chord_segments(events, dur, y=None, sr=22050, win=2.0, hop=2.0, spans=None):
    """Fit the historical templates without changing their evidence gates.

    The old beat-tracking branch is intentionally removed. Event IDs are indices
    into this function's input; production uses the entire original event list.
    """
    if spans is None:
        if win <= 0 or hop <= 0:
            raise ValueError("和弦窗宽和步长必须为正数")
        spans = [(float(t), min(dur, float(t) + win)) for t in np.arange(0, dur, hop)]
    segs = []
    for index, (a, b) in enumerate(spans):
        sub = [(i, event) for i, event in enumerate(events) if event[0] < b and event[1] > a]
        v = np.zeros(12)
        for _, (s, e, p, am) in sub:
            overlap = max(0.0, min(e, b) - max(s, a))
            register_weight = 1.0 + 0.5 * max(-1.0, min(1.0, (60 - p) / 24.0))
            v[p % 12] += overlap * (0.3 + am) * register_weight
        v /= v.sum() + 1e-9
        detected = [int(pc) for pc in np.flatnonzero(v > 1e-9)]
        segment = {"id": f"c{index:05d}", "t": round(a, 1), "t0": float(a), "t1": float(b),
                   "dur": round(b - a, 2), "root": None, "q": "", "fit": None,
                   "status": "insufficient_evidence", "reason": None,
                   "event_count": len(sub), "distinct_pitch_classes": len(detected),
                   "detected_pitch_classes": detected,
                   "pitch_class_weights": [round(float(x), 9) for x in v],
                   "source_event_ids": [f"e{i:06d}" for i, _ in sub],
                   "support_event_ids": [], "chord_pitch_classes": [],
                   "supported_pitch_classes": [], "missing_pitch_classes": [],
                   "support_count": 0, "required_tone_count": 0}
        if len(sub) < 3:
            segment['reason'] = 'fewer_than_three_events'
        elif len(detected) < 2:
            segment['reason'] = 'fewer_than_two_pitch_classes'
        else:
            candidates = []
            for quality, intervals in CHORD_SHAPES.items():
                for root in range(12):
                    tones = [(root + i) % 12 for i in intervals]
                    supported = [t for t in tones if v[t] >= 0.04]
                    if len(intervals) >= 4:
                        if v[(root + intervals[3]) % 12] < 0.12 or len(supported) < 3:
                            continue
                    elif len(supported) < 2:
                        continue
                    missing = 1.0 - len(supported) / len(tones)
                    inside = v[tones].sum()
                    score = inside - 0.55 * (v.sum() - inside)
                    score -= 0.20 * (len(intervals) - 3)
                    score -= 0.45 * missing
                    candidates.append((float(score), root, quality, tones, supported))
            # Stable sort preserves the original template tie-breaking order.
            candidates.sort(key=lambda c: -c[0])
            if candidates:
                score, root, quality, tones, supported = candidates[0]
                segment.update(root=root, q=quality, fit=round(score, 3),
                    status='candidate' if len(supported) == len(tones) else 'incomplete_support',
                    reason='template_fit_not_verified_harmony', chord_pitch_classes=tones,
                    supported_pitch_classes=supported,
                    missing_pitch_classes=[t for t in tones if t not in supported],
                    support_count=len(supported), required_tone_count=len(tones),
                    support_event_ids=[f"e{i:06d}" for i, e in sub if e[2] % 12 in supported],
                    runner_up=({"root_pc": candidates[1][1], "quality": candidates[1][2],
                                "score": round(candidates[1][0], 6)} if len(candidates) > 1 else None),
                    score_margin=(round(score - candidates[1][0], 6) if len(candidates) > 1 else None))
            else:
                segment['reason'] = 'no_candidate_passed_evidence_gates'
        segs.append(segment)
    return segs


def diatonic(tonic, mode):
    sc = SCALES[mode]
    out = set()
    for i, r in enumerate(sc):
        out.add(((tonic + r) % 12, DEGREE_Q[mode][i]))
        seventh = (["maj7", "m7", "m7", "maj7", "7", "m7", "m7b5"] if mode == "major"
                   else ["m7", "m7b5", "maj7", "m7", "m7", "maj7", "7"])
        out.add(((tonic + r) % 12, seventh[i]))
    if mode == "minor":                      # 和声小调的属大三也允许
        out.add(((tonic + 7) % 12, ""))
        out.add(((tonic + 7) % 12, "7"))
    return out


def functional_scores(chords):
    """给 24 个调打分：调内和弦占比（按时长加权）+ 收束和弦是否主和弦 + 终止式。"""
    valid = [c for c in chords if c["root"] is not None]
    res = {}
    for tonic in range(12):
        for mode in ("major", "minor"):
            if not valid:
                res[(tonic, mode)] = 0.0
                continue
            dia = diatonic(tonic, mode)
            tot = sum(c["dur"] for c in valid) or 1.0
            ratio = sum(c["dur"] for c in valid if (c["root"], c["q"]) in dia) / tot
            tonic_triad = (tonic, "" if mode == "major" else "m")
            tonic_qualities = {tonic_triad[1], "maj7" if mode == "major" else "m7"}

            # 收束：最后 4 个和弦按时长 × 越靠后权重越大（1,2,3,4）投票
            tail = {}
            last4 = valid[-4:]
            for i, c in enumerate(last4):
                key = (c["root"], c["q"])
                tail[key] = tail.get(key, 0.0) + c["dur"] * (i + 1)
            closing = max(tail, key=tail.get) if tail else (None, "")
            bonus = 0.0
            if closing[0] == tonic and closing[1] in tonic_qualities:
                bonus += 0.95
            if valid[0]["root"] == tonic and valid[0]["q"] in tonic_qualities:
                bonus += 0.40
            # 终止式：倒数第二个不同的和弦 -> 收束和弦
            if closing[0] == tonic and len(valid) >= 2:
                prev = None
                for c in reversed(valid[:-1]):
                    if (c["root"], c["q"]) != closing:
                        prev = c
                        break
                if prev is not None:
                    gap = (prev["root"] - tonic) % 12
                    bonus += {7: 0.65, 10: 0.30, 5: 0.25, 11: 0.20}.get(gap, 0.0)
            res[(tonic, mode)] = ratio + bonus
    return res


def roman(c, tonic, mode):
    """Diatonic degrees first; otherwise spell a lowered degree (Db = flat II)."""
    if c['root'] is None or tonic is None:
        return None
    pc = (c['root'] - tonic) % 12
    scale = SCALES[mode]
    degrees = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII']
    def quality(degree):
        q = c['q']
        degree = degree.lower() if q in ('m', 'dim', 'm7', 'm7b5') else degree
        return degree + {'dim': '°', 'aug': '+', 'maj7': 'maj7', 'm7': '7',
                         '7': '7', 'm7b5': 'ø7'}.get(q, '')
    if pc in scale:
        return quality(degrees[scale.index(pc)])
    for index, degree_pc in enumerate(scale):
        if pc == (degree_pc - 1) % 12:
            return '♭' + quality(degrees[index])
    return '?'


def confidence(fused: dict, tau: float = 0.18) -> dict:
    """相对置信度：对合成分数做温度 softmax。是内部相对量，不是真概率。"""
    mx = max(fused.values())
    ex = {k: math.exp((v - mx) / tau) for k, v in fused.items()}
    s = sum(ex.values())
    return {k: v / s for k, v in ex.items()}


def key_stability(fused, d_note, d_bass, chroma, func, wks, selected_key=None,
                  evidence_sufficient=True):
    """Two diagnostics against the final decision; temperature is informational."""
    tables = dict(zip(SOURCE_NAMES, [key_table(d_note), key_table(d_bass), key_table(chroma), func]))
    best = selected_key if selected_key is not None else select_key(fused, tables)[0]
    if not evidence_sufficient:
        best = None
    sweep = []
    for tau in (0.10, 0.18, 0.30):
        conf = confidence(fused, tau)
        winner = max(conf, key=conf.get) if has_scores(fused) else None
        sweep.append({'tau': tau, 'key': key_label(winner) if winner else None,
                      'share': float(conf[winner]) if winner else None})
    loo = []
    for index, name in enumerate(SOURCE_NAMES):
        weights = [0.30, 0.18, 0.15, 0.37]
        weights[index] = 0.0
        tab = fuse(d_note, d_bass, chroma, func, w=weights)
        reduced = {n: t for n, t in tables.items() if n != name}
        winner = select_key(tab, reduced)[0] if evidence_sufficient else None
        applicable = has_scores(tables[name]) and best is not None
        loo.append({'omitted': name, 'key': key_label(winner) if winner else None,
                    'applicable': applicable, 'agrees': applicable and winner == best})
    applicable = [row for row in loo if row['applicable']]
    valid = [window for window in wks if window['key'] is not None]
    matching = sum(tuple(window['key']) == best for window in valid)
    ratio = matching / len(valid) if valid and best is not None else None
    checks = [bool(applicable) and all(row['agrees'] for row in applicable),
              ratio is not None and ratio >= 0.5]
    return {'summary': f'{sum(checks)}/2 项通过', 'passed': sum(checks), 'total': 2,
            'reference_key': key_record(best),
            'tau_sweep': {'informational_only': True, 'results': sweep,
                          'note': '正温度保持排名，不计入通过数；份额不是概率。'},
            'leave_one_out': {'passed': checks[0], 'agree_count': sum(x['agrees'] for x in applicable),
                              'total': len(applicable), 'results': loo,
                              'note': '比较最终决策，包含三票修正规则；不是独立确认。'},
            'segment_consistency': {'passed': checks[1], 'matching_windows': matching,
                'valid_windows': len(valid), 'total_windows': len(wks), 'ratio': ratio, 'threshold': 0.5,
                'note': '重叠窗口不是独立样本；变化可能来自真实转调或误判，不表示正确率。'}}


# ----------------------------------------------------------------------------- 音频


def load_audio(path: Path, sr: int = 22050):
    """读音频。

    librosa 读 m4a/aac 要走 audioread 后端，本机没有，会抛 NoBackendError。
    失败时改用 imageio-ffmpeg（自带 ffmpeg 二进制，装在环境里即可，不碰系统）
    转成 wav 再读，这样拖 mp3/m4a 进来不用先自己转格式。
    """
    import librosa
    try:
        y, sr = librosa.load(str(path), sr=sr, mono=True)
        return y, sr
    except Exception as first_exc:
        try:
            import imageio_ffmpeg
        except ImportError:
            raise RuntimeError(
                f"{path.name} 无法解码（{type(first_exc).__name__}）。"
                f"请先转成 wav，或在环境里安装 imageio-ffmpeg："
                f"pip install imageio-ffmpeg") from first_exc

        import subprocess
        import tempfile
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = Path(f.name)
        try:
            proc = subprocess.run(
                [exe, "-y", "-loglevel", "error", "-i", str(path),
                 "-ac", "1", "-ar", str(sr), str(tmp)],
                capture_output=True)
            if proc.returncode != 0:
                msg = proc.stderr.decode("utf-8", "ignore").strip()[:300]
                raise RuntimeError(f"{path.name} 转码失败：{msg}") from first_exc
            y, sr = librosa.load(str(tmp), sr=sr, mono=True)
            return y, sr
        finally:
            tmp.unlink(missing_ok=True)


def ensure_decodable(path: Path, out_dir: Path) -> Path:
    """确保下游（Basic Pitch / Demucs）能读到这个文件。

    只在原格式读不了时才转码，结果落成 out_dir/_input.wav 供后续复用，
    避免 load_audio 和 transcribe 各转一遍。能直接读的文件原样返回。
    """
    try:
        import librosa
        librosa.load(str(path), sr=22050, mono=True, duration=0.5)  # 试探开头
        return path
    except Exception:
        pass

    try:
        import imageio_ffmpeg
    except ImportError:
        raise RuntimeError(
            f"{path.name} 本机无法解码，且没有 imageio-ffmpeg 可兜底。\n"
            f"请转成 wav，或执行：pip install imageio-ffmpeg")

    import subprocess
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    dst = out_dir / "_input.wav"
    proc = subprocess.run(
        [exe, "-y", "-loglevel", "error", "-i", str(path),
         "-ac", "1", "-ar", "22050", str(dst)],
        capture_output=True)
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", "ignore").strip()[:300]
        raise RuntimeError(f"{path.name} 转码失败：{msg}")
    print(f"      {path.suffix} 无法直接解码，已转码为 _input.wav", flush=True)
    return dst


def chroma_profile(y, sr) -> np.ndarray:
    """音频色度（HPCP 近似）：先做谐波增强，再按帧能量加权累加。"""
    import librosa
    y_h = librosa.effects.harmonic(y, margin=3.0)
    ch = librosa.feature.chroma_cqt(y=y_h, sr=sr, bins_per_octave=36, hop_length=512)
    rms = librosa.feature.rms(y=y_h, hop_length=512)[0]
    n = min(ch.shape[1], rms.shape[0])
    ch, rms = ch[:, :n], rms[:n]
    ch = ch / (ch.sum(axis=0, keepdims=True) + 1e-9)
    w = rms ** 2
    prof = (ch * w).sum(axis=1)
    return prof / (prof.sum() + 1e-9)


def estimate_tempo(y, sr) -> float:
    import librosa
    oenv = librosa.onset.onset_strength(y=y, sr=sr)
    bpm = librosa.feature.tempo(onset_envelope=oenv, sr=sr, aggregate=np.median)
    bpm = float(np.atleast_1d(bpm)[0])
    while bpm < 60:
        bpm *= 2
    while bpm > 180:
        bpm /= 2
    return round(bpm, 1)


# ----------------------------------------------------------------------------- 转录
def transcribe(path: Path):
    from basic_pitch.inference import predict
    from basic_pitch import ICASSP_2022_MODEL_PATH
    _, midi_data, note_events = predict(
        str(path), ICASSP_2022_MODEL_PATH,
        **TRANSCRIPTION_PARAMETERS,
    )
    ev = []
    for t in note_events:
        s, e, p, a = float(t[0]), float(t[1]), int(t[2]), float(t[3])
        if e - s < 0.045:
            continue
        ev.append((s, e, p, a))
    ev.sort(key=lambda x: (x[0], x[2]))
    return ev, midi_data


def merge_events(*event_lists, tol: float = 0.03):
    """Match same-pitch starts to a fixed cluster anchor, retaining one whole event.

    Fixed anchors avoid transitive chaining. Real repeated notes inside tol can
    still be merged; this is an explicit heuristic, not instrument identification.
    """
    if not math.isfinite(tol) or tol <= 0:
        raise ValueError('去重时间容差必须为有限正数')
    by_pitch = {}
    for events in event_lists:
        for event in events:
            by_pitch.setdefault(int(event[2]), []).append(event)
    merged = []
    for pitch_events in by_pitch.values():
        pitch_events.sort(key=lambda e: (e[0], -e[3], e[1]))
        anchor, selected = None, None
        for event in pitch_events:
            if anchor is None or event[0] - anchor > tol:
                if selected is not None:
                    merged.append(selected)
                anchor, selected = event[0], event
            elif event[3] > selected[3]:
                selected = event
        if selected is not None:
            merged.append(selected)
    return sorted(merged, key=lambda e: (e[0], e[2]))


def events_to_midi(events, path, tempo: float = 120.0):
    """把合并后的事件写成 MIDI（分离模式下 basic_pitch 的 midi 没法直接用）。"""
    import pretty_midi
    pm = pretty_midi.PrettyMIDI(initial_tempo=tempo)
    inst = pretty_midi.Instrument(program=0)
    for s, e, p, a in events:
        inst.notes.append(pretty_midi.Note(
            velocity=int(min(127, 40 + 90 * a)), pitch=int(p), start=float(s), end=float(e)))
    pm.instruments.append(inst)
    pm.write(str(path))


def run_separation(src: Path, stem_dir: Path, stems: str, model: str = "htdemucs"):
    """Demucs 分轨 -> 逐轨转录 -> 合并。返回统计信息与合并后的事件。"""
    script = Path(__file__).resolve().parent / "split_stems.py"
    if not script.exists():
        raise SystemExit(f"找不到分轨脚本：{script}")
    print(f"[sep] Demucs {model} 分轨中（需要 GPU 时自动借用，CPU 约每首 3-8 分钟）...", flush=True)
    t0 = time.time()
    proc = subprocess.run([sys.executable, str(script), str(src), "-o", str(stem_dir),
                           "--model", model, "--quiet"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-1500:]
        raise SystemExit(f"分轨失败：\n{tail}")
    head = [ln for ln in (proc.stdout or "").splitlines() if "device=" in ln]
    device = head[0].split("device=")[1].split()[0] if head else "unknown"
    sep_seconds = time.time() - t0

    wanted = [s.strip() for s in stems.split(",") if s.strip()]
    per_stem, evs = {}, []
    for name in wanted:
        p = stem_dir / f"{name}.wav"
        if not p.exists():
            raise SystemExit(f"声部 {name} 不存在，可用：drums / bass / other / vocals")
        ev, _ = transcribe(p)
        per_stem[name] = len(ev)
        evs.append(ev)
        print(f"      {name}: {len(ev)} 事件", flush=True)
    merged = merge_events(*evs)
    print(f"[sep] 合并去重后 {len(merged)} 个事件（分轨耗时 {sep_seconds:.0f}s，{device}）", flush=True)
    return {"stems": wanted, "per_stem": per_stem, "device": device,
            "seconds": round(sep_seconds, 1), "merged": len(merged)}, merged


# ----------------------------------------------------------------------------- 统计
def pc_hist(events, t0=None, t1=None, clip=True) -> np.ndarray:
    h = np.zeros(12)
    for s, e, p, a in events:
        if t0 is not None:
            s2, e2 = max(s, t0), min(e, t1)
            if e2 <= s2:
                continue
            w = (e2 - s2) * (0.3 + a)
        else:
            w = (e - s) * (0.3 + a)
        h[p % 12] += w
    if clip:  # 对数压缩，避免个别长音吃掉直方图
        m = h.max()
        if m > 0:
            h = np.log1p(9 * h / m)
    return h


def bass_hist(events) -> np.ndarray:
    h = np.zeros(12)
    if not events:
        return h
    groups, cur = [], [events[0]]
    for ev in events[1:]:
        if ev[0] - cur[-1][0] <= 0.06:
            cur.append(ev)
        else:
            groups.append(cur)
            cur = [ev]
    groups.append(cur)
    for g in groups:
        low = min(g, key=lambda x: x[2])
        h[low[2] % 12] += (low[1] - low[0]) * (0.3 + low[3]) * 2.0
    m = h.max()
    return np.log1p(9 * h / m) if m > 0 else h


KEY_WINDOW_SECONDS = 12.0


def window_keys(events, dur, win=KEY_WINDOW_SECONDS, hop=3.0, y=None, sr=22050):
    out = []
    t = 0.0
    while t + win <= dur + 1e-6:
        sub = [e for e in events if e[0] < t + win and e[1] > t]
        n = len(sub)
        if n >= 8:
            ch = chord_segments(sub, win, None, sr, spans=[(t, t + win)])
            f = fuse(pc_hist(events, t, t + win), bass_hist(sub), None,
                     functional_scores(ch), w=(0.34, 0.22, 0.0, 0.44))
            best = max(f, key=f.get)
            out.append({"t": round(t, 1), "key": best, "notes": n,
                        "score": round(float(f[best]), 3)})
        else:
            out.append({"t": round(t, 1), "key": None, "notes": n, "score": 0.0})
        t += hop
    return out


def segments(wks, win=KEY_WINDOW_SECONDS):
    segs = []
    for w in wks:
        if w["key"] is None:
            continue
        if segs and segs[-1]["key"] == w["key"] and w["t"] - segs[-1]["t1"] <= 3.01:
            segs[-1]["t1"] = w["t"] + win
            segs[-1]["n"] += 1
        else:
            segs.append({"key": w["key"], "t0": w["t"], "t1": w["t"] + win, "n": 1})
    segs = [s for s in segs if s["n"] >= 2]
    for current, following in zip(segs, segs[1:]):
        current["t1"] = min(current["t1"], following["t0"])
    return segs


# ----------------------------------------------------------------------------- 记谱
def quantize(events, bpm, q=0.25, origin=0.0):
    spb = 60.0 / bpm
    out = []
    for s, e, p, a in events:
        if e <= origin:
            continue
        s = max(s, origin)
        o = round((s - origin) / spb / q) * q
        d = max(q, round((e - s) / spb / q) * q)
        out.append({"o": round(o, 4), "d": round(d, 4), "p": p, "a": a})
    return out


SINGLE_STAFF_MAX_POLY_RATIO = 0.08
SINGLE_STAFF_MAX_PITCH_SPAN = 30


def _staff_metrics(qn):
    """Count notes at each quantized onset, rather than overlapping durations."""
    onsets = {}
    for x in qn:
        onsets[x["o"]] = onsets.get(x["o"], 0) + 1
    pitches = [x["p"] for x in qn]
    return {"poly_ratio": sum(n >= 2 for n in onsets.values()) / len(onsets) if onsets else 0.0,
            "pitch_span": int(max(pitches) - min(pitches)) if pitches else 0,
            "median_pitch": int(np.median(pitches)) if pitches else 60}


def detect_staves(qn):
    """Use one staff only for sparse onsets within a compact pitch range."""
    info = _staff_metrics(qn)
    single = (info["poly_ratio"] <= SINGLE_STAFF_MAX_POLY_RATIO
              and info["pitch_span"] <= SINGLE_STAFF_MAX_PITCH_SPAN)
    limits = []
    if info["poly_ratio"] > SINGLE_STAFF_MAX_POLY_RATIO:
        limits.append(f"多音起音占比超过 {SINGLE_STAFF_MAX_POLY_RATIO:.1%}")
    if info["pitch_span"] > SINGLE_STAFF_MAX_PITCH_SPAN:
        limits.append(f"音域超过 {SINGLE_STAFF_MAX_PITCH_SPAN} 半音")
    reason = "检测为单声部素材" if single else "、".join(limits)
    reason += f'（多音起音占比 {info["poly_ratio"]:.1%}，音域 {info["pitch_span"]} 半音）'
    return {"n_staves": 1 if single else 2, "reason": reason, **info}


def resolve_staves(qn, staves="auto"):
    if staves == "auto":
        return detect_staves(qn)
    if str(staves) not in ("1", "2"):
        raise ValueError("staves must be auto, 1 or 2")
    return {"n_staves": int(staves), "reason": f"命令行强制 {staves} 个谱表", **_staff_metrics(qn)}


def split_voices(qn, q=0.25):
    pitches = np.array([x["p"] for x in qn])
    split = int(np.percentile(pitches, 38)) if len(pitches) else 60
    split = min(max(split, 48), 67)
    up = [x for x in qn if x["p"] >= split]
    lo = [x for x in qn if x["p"] < split]
    return up, lo, split


def group_onsets(items, max_notes, q=0.25):
    by = {}
    for x in items:
        by.setdefault(round(x["o"], 3), []).append(x)
    out = []
    for o in sorted(by):
        g = sorted(by[o], key=lambda z: z["p"])
        if len(g) > max_notes:  # 保留最响的若干个音
            g = sorted(sorted(g, key=lambda z: -z["a"])[:max_notes], key=lambda z: z["p"])
        ps, seen = [], set()
        for x in g:
            if x["p"] not in seen:
                seen.add(x["p"])
                ps.append(x["p"])
        out.append({"o": o, "ps": ps, "d": max(x["d"] for x in g), "a": max(x["a"] for x in g)})
    # 长度截止到下一个 onset，避免纵向重叠
    for i in range(len(out) - 1):
        out[i]["d"] = max(q, min(out[i]["d"], round((out[i + 1]["o"] - out[i]["o"]) * 4) / 4))
    return out


def duration_lanes(items):
    """Partition quantized intervals into non-overlapping notation voices.

    Lanes preserve every input interval; they do not infer musical voices or hands.
    """
    lanes, ends = [], []
    for item in sorted(items, key=lambda x: (x['o'], x['p'], x['d'])):
        available = next((i for i, end in enumerate(ends) if end <= item['o'] + 1e-9), None)
        if available is None:
            lanes.append([])
            ends.append(0.0)
            available = len(lanes) - 1
        lanes[available].append(item)
        ends[available] = item['o'] + item['d']
    return lanes


def build_score(qn, bpm, tonic_pc, mode, mode_sel="reduction", ts=(4, 4), segs=None,
                staves="auto", origin=0.0):
    from music21 import stream, note, chord, meter, key as m21key, tempo as m21tempo, clef, layout

    staff_info = resolve_staves(qn, staves)
    if staff_info["n_staves"] == 1:
        c = clef.BassClef() if staff_info["median_pitch"] <= 52 else clef.TrebleClef()
        groups = ((qn if mode_sel == 'full' else group_onsets(qn, 3), c),)
    else:
        up, lo, split = split_voices(qn)
        up_g = up if mode_sel == 'full' else group_onsets(up, 3)
        lo_g = lo if mode_sel == 'full' else group_onsets(lo, 2)
        groups = ((up_g, clef.TrebleClef()), (lo_g, clef.BassClef()))

    sc = stream.Score()
    sc.editorial['preserve_notation_lanes'] = mode_sel == 'full'
    parts = []
    for grp, c in groups:
        p = stream.PartStaff()
        if mode_sel == 'full':
            for index, lane in enumerate(duration_lanes(grp)):
                voice = stream.Voice(id=index + 1)
                for item in lane:
                    el = note.Note(item['p'])
                    # makeMeasures renumbers voices and makeTies can flatten a
                    # singleton voice. Keep the original lane on split copies.
                    el.editorial['notation_lane'] = index
                    el.duration.quarterLength = item['d']
                    el.volume.velocity = int(min(127, 35 + 90 * item['a']))
                    voice.insert(item['o'], el)
                p.insert(0, voice)
        else:
            for g in grp:
                el = note.Note(g["ps"][0]) if len(g["ps"]) == 1 else chord.Chord(g["ps"])
                el.duration.quarterLength = g["d"]
                el.volume.velocity = int(min(127, 35 + 90 * g["a"]))
                p.insert(g["o"], el)
        p.insert(0, c)
        parts.append(p)

    for p in parts:
        sc.insert(0, p)
    # 调号 / 拍号 / 速度必须写进每个声部的第 1 小节，
    # 只插在总谱层的话，makeMeasures 走的是声部，导出时会被丢掉（谱面就变成无调号）。
    bar_s = bar_seconds(bpm, ts)
    time_signature = meter.TimeSignature(f"{ts[0]}/{ts[1]}")
    bar_quarters = time_signature.barDuration.quarterLength
    # Resolve segments that snap to the same bar before suppressing redundant keys.
    keys_by_measure = {0: (tonic_pc, mode)} if tonic_pc is not None else {}
    for segment in sorted(segs or [], key=lambda s: s["t0"]):
        if segment["n"] >= 2:
            measure_index = max(0, round(max(0, segment["t0"] - origin) / bar_s))
            keys_by_measure[measure_index] = tuple(segment["key"])
    active_key = None
    key_changes = []
    for measure_index, segment_key in sorted(keys_by_measure.items()):
        if segment_key != active_key:
            key_changes.append((measure_index * bar_quarters, segment_key))
            active_key = segment_key
    for p in parts:
        p.insert(0, meter.TimeSignature(f"{ts[0]}/{ts[1]}"))
        for offset, (pc, key_mode) in key_changes:
            p.insert(offset, m21key.Key(KEY_SPELLINGS[key_mode][pc], key_mode))
    parts[0].insert(0, m21tempo.MetronomeMark(number=bpm))
    if len(parts) == 2:
        try:
            sc.insert(0, layout.StaffGroup(parts, symbol="brace", barTogether=True))
        except Exception:
            pass

    for p in parts:
        try:
            p.makeMeasures(inPlace=True)
            p.makeTies(inPlace=True)
            p.makeNotation(inPlace=True)
        except Exception as exc:
            raise RuntimeError(f"记谱整理失败，不能将未完成的谱面当作成功产物：{exc}") from exc
    return sc


def write_score_musicxml(score, path):
    """Export prepared notation without changing tie-chain voice identities.

    Full-mode lanes are mechanical interval partitions, not inferred musical
    voices. music21's default PartStaff export can renumber a lower staff in
    just one measure when the upper staff has a singleton/zero-numbered voice.
    Restore positive, globally distinct lane IDs after notation and duration
    splitting, then serialize without another makeNotation pass.
    """
    if not score.editorial.get('preserve_notation_lanes', False):
        return score.write('musicxml', fp=str(path))
    from music21 import stream, note

    prepared = score.splitAtDurations(recurse=True)[0]
    next_voice_id = 1
    for part in prepared.parts:
        lane_ids = sorted({n.editorial['notation_lane'] for n in part.recurse().notes})
        voice_ids = {lane: next_voice_id + i for i, lane in enumerate(lane_ids)}
        next_voice_id += max(1, len(lane_ids))
        for measure in part.getElementsByClass(stream.Measure):
            lanes = {}
            # Collect offsets before detaching voices; ties retain their lane
            # even when the previous notation pass flattened a singleton.
            for n in list(measure.recurse().notes):
                lane = n.editorial['notation_lane']
                lanes.setdefault(lane, []).append((n.getOffsetInHierarchy(measure), n))
            for voice in list(measure.voices):
                measure.remove(voice)
            for n in list(measure.notesAndRests):
                measure.remove(n)
            if not lanes:
                # An explicit voice also prevents per-measure renumbering of
                # the other staff when this staff is completely silent.
                voice = stream.Voice(id=min(voice_ids.values(), default=next_voice_id - 1))
                voice.insert(0, note.Rest(quarterLength=measure.barDuration.quarterLength))
                measure.insert(0, voice)
            for lane, members in sorted(lanes.items()):
                voice = stream.Voice(id=voice_ids[lane])
                for offset, n in members:
                    voice.insert(offset, n)
                voice.makeRests(refStreamOrTimeRange=[0, measure.barDuration.quarterLength],
                                fillGaps=True, inPlace=True)
                measure.insert(0, voice)
    # Gap-filling rests can themselves have composite durations.
    prepared = prepared.splitAtDurations(recurse=True)[0]
    return prepared.write('musicxml', fp=str(path), makeNotation=False)


def render_svg(xml_path: Path, out_dir: Path):
    import verovio
    tk = verovio.toolkit()
    try:
        rp = Path(verovio.__file__).parent / "data"
        if rp.exists():
            tk.setResourcePath(str(rp))
    except Exception:
        pass
    tk.setOptions({"scale": 42, "adjustPageHeight": True,
                   "pageWidth": 2100, "pageHeight": 2970,
                   "breaks": "auto", "footer": "none", "header": "none"})
    ok = tk.loadFile(str(xml_path))
    if not ok:
        return []
    svgs = []
    for i in range(1, tk.getPageCount() + 1):
        svg = tk.renderToSVG(i)
        fp = out_dir / f"score_p{i}.svg"
        fp.write_text(svg, encoding="utf-8")
        svgs.append(svg)
    return svgs


# ----------------------------------------------------------------------------- 图
def svg_timeline(segs, dur, wks):
    W, H = 900, 96
    x = lambda t: 60 + (W - 110) * (t / max(dur, 1))
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px">']
    parts.append(f'<rect x="60" y="26" width="{W-110}" height="26" rx="4" fill="#eee8dd"/>')
    palette = ["#7a3e2f", "#3f5f6f", "#5b6b3a", "#8a6a2f", "#6a4a6f"]
    prev_end = 0.0
    for i, s in enumerate(segs):
        col = palette[i % len(palette)]
        a0 = max(0.0, s["t0"], prev_end)
        x0, x1 = x(a0), x(min(dur, s["t1"]))
        prev_end = max(prev_end, s["t1"])
        parts.append(f'<rect x="{x0:.1f}" y="26" width="{max(2,x1-x0):.1f}" height="26" rx="3" fill="{col}" opacity="0.85"/>')
        if x1 - x0 > 46:
            nm = f'{PC_NAMES[s["key"][0]]} {"大" if s["key"][1]=="major" else "小"}调'
            parts.append(f'<text x="{(x0+x1)/2:.1f}" y="44" text-anchor="middle" font-size="11" fill="#fff" font-family="system-ui">{html.escape(nm)}</text>')
    for t in range(0, int(dur) + 1, max(10, int(dur // 8))):
        parts.append(f'<text x="{x(t):.1f}" y="72" text-anchor="middle" font-size="10" fill="#777" font-family="system-ui">{t}s</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_density(events, dur):
    bins = max(1, int(dur))
    d = np.zeros(bins)
    for s, e, p, a in events:
        b = int(s)
        if 0 <= b < bins:
            d[b] += 1
    W, H, pad = 900, 130, 46
    m = max(d.max(), 1)
    bw = (W - 2 * pad) / bins
    bars = [f'<rect x="{pad + i*bw:.1f}" y="{H-26-(d[i]/m)*72:.1f}" width="{max(0.6,bw-0.8):.1f}" '
            f'height="{(d[i]/m)*72:.1f}" fill="#3f5f6f" opacity="0.75"/>' for i in range(bins)]
    axis = [f'<line x1="{pad}" y1="{H-26}" x2="{W-pad}" y2="{H-26}" stroke="#ccc"/>']
    labels = [f'<text x="{pad}" y="{H-8}" font-size="10" fill="#777" font-family="system-ui">0s</text>',
              f'<text x="{W-pad}" y="{H-8}" font-size="10" fill="#777" text-anchor="end" font-family="system-ui">{int(dur)}s</text>',
              f'<text x="{pad}" y="{H-32-72}" font-size="10" fill="#777" font-family="system-ui">峰值 {int(m)} 音/秒</text>']
    return f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px">{"".join(bars+axis+labels)}</svg>'


def key_grid(fused, conf, best):
    cells = []
    for mode in ("major", "minor"):
        row = []
        for t in range(12):
            k = (t, mode)
            v = conf[k]
            rel = v / max(conf.values())
            bg = f"rgba(122,62,47,{0.08 + 0.72*rel:.2f})"
            fg = "#fff" if rel > 0.55 else "#3a3a3a"
            ring = "outline:2px solid #1a1a1a;" if k == best else ""
            row.append(f'<div class="cell" style="background:{bg};color:{fg};{ring}">'
                       f'<b>{PC_NAMES[t]}{"m" if mode=="minor" else ""}</b><span>{v*100:.1f}</span></div>')
        cells.append(f'<div class="grid">{ "".join(row) }</div>')
    return "".join(cells)


# This file is spliced into the standalone production script after svg helpers.
def file_fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return {'name': Path(path).name, 'bytes': Path(path).stat().st_size, 'sha256': digest.hexdigest()}


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


@lru_cache(maxsize=24)
def pitch_spellings(tonic, mode):
    from music21 import key as m21key
    key = m21key.Key(KEY_SPELLINGS[mode][tonic], mode)
    names = list(PC_NAMES if key.sharps >= 0 else
                 ('C', 'D-', 'D', 'E-', 'E', 'F', 'G-', 'G', 'A-', 'A', 'B-', 'B'))
    for pitch in key.pitches:
        names[pitch.pitchClass] = pitch.name
    return tuple(name.replace('-', '♭').replace('#', '♯') for name in names)


def describe_chords(chords, segs, best):
    for c in chords:
        midpoint = (c['t0'] + c['t1']) / 2
        local_index = next((i for i, s in enumerate(segs) if s['t0'] <= midpoint < s['t1']), None)
        local_key = segs[local_index]['key'] if local_index is not None else best
        c['key_basis'] = {'kind': 'window_segment' if local_index is not None else 'global_candidate',
                          'segment_id': f's{local_index:04d}' if local_index is not None else None,
                          'key': key_record(local_key)}
        c['crosses_key_boundary'] = any(c['t0'] < s['t0'] < c['t1'] for s in segs)
        c['roman'] = roman(c, *local_key) if local_key is not None else None
        c['root_pc'] = c['root']
        c['quality'] = c['q']
        c['label'] = ((pitch_spellings(*local_key)[c['root']] if local_key else PC_NAMES[c['root']])
                      + c['q']) if c['root'] is not None else None
        c['fit_kind'] = 'uncalibrated_template_score'


def evaluate_decision(best, fused, consensus, events, signal_rms):
    reasons = []
    if len(events) < 8:
        reasons.append('fewer_than_eight_note_events')
    if signal_rms <= 1e-7:
        reasons.append('near_digital_silence')
    if best is None:
        reasons.append('no_informative_score_path')
    ordered = sorted(fused.values(), reverse=True)
    margin = float(ordered[0] - ordered[1]) if len(ordered) >= 2 else None
    if reasons:
        state = 'insufficient_evidence'
    else:
        if consensus['agree'] < 3:
            reasons.append('fewer_than_three_paths_agree')
        if consensus['available'] < 4:
            reasons.append('some_paths_unavailable')
        if margin is not None and margin < 0.25:
            reasons.append('small_fusion_margin')
        if consensus['corrected']:
            reasons.append('fusion_overridden_by_historical_consensus_rule')
        state = 'ambiguous' if reasons else 'candidate'
    return {'status': state, 'reasons': reasons, 'fusion_margin': margin,
            'calibrated': False,
            'policy': {'min_note_events': 8, 'silence_rms_max': 1e-7, 'small_margin_below': 0.25,
                       'note': '透明的保守规则，未经真实数据校准；candidate 也不表示已确认。'}}


def score_counts(qn, staves, mode):
    if staves['n_staves'] == 2:
        up, lo, split = split_voices(qn)
        groups = group_onsets(up, 3) + group_onsets(lo, 2)
    else:
        split = None
        groups = group_onsets(qn, 3)
    return {'quantized_input_notes': len(qn),
            'retained_notes_before_ties': len(qn) if mode == 'full' else sum(len(g['ps']) for g in groups),
            'split_pitch': split,
            'independent_quantized_durations': mode == 'full',
            'pitch_or_onset_cap': None if mode == 'full' else {'upper_or_single': 3, 'lower': 2},
            'limitations': ('保留每个量化音符的独立时值；排版声部是区间分组，不是乐器或手部识别。'
                           if mode == 'full' else '阅读用简化谱；同组统一时值、下一起音截断，不是完整转录。')}


def make_summary(data):
    summary = {key: data[key] for key in ('schema_version', 'tool_version', 'duration', 'key', 'key_decision',
            'ranking_share', 'confidence_kind', 'bpm', 'bpm_source', 'bpm_unit', 'ts', 'ts_source',
            'bar_origin_seconds', 'notes', 'chord_coverage', 'warnings', 'evidence_files', 'artifacts')}
    summary['source'] = data['provenance']['input']
    if 'semantics' in data:
        summary['semantics'] = data['semantics']
    return summary


def render_report(data, svgs, out):
    escape = lambda x: html.escape(str(x))
    status_names = {'candidate': '候选结论', 'ambiguous': '存在歧义', 'insufficient_evidence': '证据不足'}
    coverage = data['chord_coverage']
    warnings_html = ''.join(f'<li>{escape(item)}</li>' for item in data['warnings'])
    candidates = ''.join(f'<tr><td>{escape(item["key"])}</td><td>{item["score"]:.3f}</td>'
                         f'<td>{item["conf"]:.2%}</td></tr>' for item in data['top'])
    paths = ''.join(f'<tr><td>{escape(name)}</td><td>{escape(key or "无有效证据")}</td></tr>'
                    for name, key in data['solo'].items())
    chords = []
    for c in data['chords']:
        missing = ','.join(str(x) for x in c['missing_pitch_classes']) or '无'
        evidence = (f'{c["support_count"]}/{c["required_tone_count"]} 个组成音有支撑；缺失音级：{missing}'
                    if c['root'] is not None else f'未判定：{c["reason"]}')
        roman_label = c['roman'] or '—'
        basis = c['key_basis']['key']
        key_text = basis['label'] if basis else '无调性依据'
        chords.append(f'<tr><td>{c["t0"]:.2f}–{c["t1"]:.2f}s</td>'
                      f'<td>{escape(c["label"] or "—")}</td><td>{escape(roman_label)}<br><small>{escape(key_text)}</small></td>'
                      f'<td>{escape(evidence)}<br><small>{c["event_count"]} 个转录事件；{escape(c["id"])}</small></td></tr>')
    checks = data['stability']
    pages = ''.join(f'<div class="page">{svg}</div>' for svg in svgs)
    if not pages:
        pages = '<p>本次未生成 SVG 谱面。请查看产物状态；有 MusicXML 时可用记谱软件打开。</p>'
    title = escape(data['title'])
    share = f'{data["ranking_share"]:.2%}' if data['ranking_share'] is not None else '不适用'
    page = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · 音乐分析</title>
<style>body{{margin:0;background:#f0eee8;color:#242424;font:15px/1.65 system-ui,"Segoe UI",sans-serif}}
main{{max-width:1050px;margin:auto;padding:26px}}section{{background:#fffdf8;padding:22px;margin:16px 0;border:1px solid #ddd7ca;border-radius:6px}}
h1{{font-size:27px}}h2{{font-size:19px}}.key{{font-size:32px;font-weight:650}}.warn{{border-left:4px solid #b87824}}
table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:8px;border-bottom:1px solid #e5e0d5;vertical-align:top}}
small,.muted{{color:#666}}.scroll{{overflow-x:auto}}.page{{background:white;margin:18px 0;overflow-x:auto}}.page svg{{max-width:100%;height:auto}}
code{{background:#eee9df;padding:2px 5px}}a{{color:#315d77}}</style></head><body><main>
<h1>{title}</h1><p>{data['duration']:.2f} 秒 · {data['notes']} 个转录事件 · {escape(data['ts'])} · {data['bpm']} 四分音符/分钟</p>
<section><h2>{status_names[data['key_decision']['status']]}</h2><div class="key">{escape(data['key'] or '证据不足，未给出调性结论')}</div>
<p>候选分数份额：{share}。这是内部相对分配，未经概率校准。</p></section>
<section class="warn"><h2>使用这些结果前请留意</h2><ul>{warnings_html}</ul></section>
<section><h2>一致性诊断：{escape(checks['summary'])}</h2>
<p>留一路：{checks['leave_one_out']['agree_count']}/{checks['leave_one_out']['total']} 个适用检查一致。
主调窗口一致比例：{escape(checks['segment_consistency']['ratio'])}。</p>
<p class="muted">温度扫描仅展示分数敏感性，不计入通过数。两项诊断均不表示正确率；真实转调也会降低窗口一致性。</p></section>
<section><h2>和弦与支撑</h2><p>{coverage['labeled_segments']}/{coverage['total_segments']} 个片段有候选和弦；
按时间覆盖 {coverage['duration_ratio']:.1%}。无结果的片段也完整保留。</p><div class="scroll"><table>
<tr><th>原音频时间</th><th>和弦候选</th><th>罗马数字与参考调性</th><th>证据</th></tr>{''.join(chords)}</table></div>
<p class="muted">音级编号 C=0，C♯/D♭=1，依次至 B=11。支撑来自模型检出的音符，不能证明真实和声；转调窗口边界为近似位置。</p></section>
<section><h2>候选排名</h2><table><tr><th>候选</th><th>融合分数</th><th>分数份额，非概率</th></tr>{candidates}</table>
<p class="muted">最终判定可能经历史三票规则修正；原融合排名保持原样，不改写成概率。</p></section>
<section><h2>各分析视角的首选</h2><table><tr><th>视角</th><th>候选</th></tr>{paths}</table>
<p class="muted">音符、低音、和弦共用同一批转录事件，票数不是独立确认次数。</p></section>
<section><h2>转调时间轴</h2>{svg_timeline([dict(s, key=(s['tonic_pc'], s['mode'])) for s in data['segments']], data['duration'], [])}
<p class="muted">12 秒窗、3 秒步进；位置不确定性按窗口尺度理解，没有验证固定 ±1 小节误差。</p></section>
<section><h2>五线谱</h2><p>模式：{escape(data['score_mode'])}；谱面零点对应原音频 {data['bar_origin_seconds']} 秒。</p>
<p>{escape(data['score_statistics']['limitations'])}</p>{pages}</section>
<section><h2>可查询证据</h2><p><a href="summary.json">简短摘要</a> · <a href="report.json">完整分析</a> · <a href="events.json">原始检测事件</a></p>
<p class="muted">识别结果与规则尚未在独立真实测试集上校准。乐器身份、歌词及曲名不在本工具的检测能力中。</p></section>
{('<section><h2>风格、类型与情感候选</h2><p>' + escape(data['semantics'].get('summary_zh', data['semantics'].get('reason', ''))) + '</p><p><a href="semantics.html">语义时间轴与限制</a> · <a href="semantics.json">完整语义证据</a></p></section>') if 'semantics' in data else ''}
</main></body></html>'''
    (out / 'report.html').write_text(page, encoding='utf-8')


def query_main(argv):
    parser = argparse.ArgumentParser(description='按原音频秒数查询已生成的证据；不重新推理')
    parser.add_argument('report', type=Path)
    parser.add_argument('--start', type=float, required=True)
    parser.add_argument('--end', type=float, required=True)
    parser.add_argument('--notes-limit', type=int, default=0,
                        help='默认不返回音符细节；上限 1000，结果含总数和截断标记')
    args = parser.parse_args(argv)
    if not (math.isfinite(args.start) and math.isfinite(args.end) and 0 <= args.start < args.end):
        parser.error('时间范围必须满足 0 <= start < end，单位为原音频秒数')
    if not 0 <= args.notes_limit <= 1000:
        parser.error('notes-limit 必须在 0..1000 之间')
    data = json.loads(args.report.read_text(encoding='utf-8'))
    if data.get('schema_version') == 'music-semantics/1.1':
        from music_semantics import query
        print(json.dumps(query(data, args.report.resolve().parent, args.start, args.end), ensure_ascii=False, allow_nan=False))
        return 0
    if data.get('schema_version') != SCHEMA_VERSION:
        parser.error('不支持该证据 schema；请使用本版生成的 report.json')
    if args.end > data['duration'] + 1e-6:
        parser.error('end 超出原音频时长')
    event_info = data['evidence_files']['events']
    folder = args.report.resolve().parent
    event_path = (folder / event_info['name']).resolve()
    if event_path.parent != folder or file_fingerprint(event_path)['sha256'] != event_info['sha256']:
        parser.error('事件文件路径或 SHA256 不匹配，拒绝输出可引用的证据')
    events = json.loads(event_path.read_text(encoding='utf-8'))['events']
    overlaps = lambda item: item['t0'] < args.end and item['t1'] > args.start
    selected = [event for event in events if overlaps(event)]
    result = {'schema_version': SCHEMA_VERSION, 'query': {'t0': args.start, 't1': args.end, 'unit': 'seconds'},
              'report': file_fingerprint(args.report), 'source': data['provenance']['input'],
              'warnings': data['warnings'], 'global_decision': data['key_decision'],
              'chords': [chord for chord in data['chords'] if overlaps(chord)],
              'segments': [segment for segment in data['segments'] if overlaps(segment)],
              'notes': selected[:args.notes_limit], 'note_count_total': len(selected),
              'notes_truncated': len(selected) > args.notes_limit,
              'evidence_files': data['evidence_files']}
    if 'semantics' in data:
        from music_semantics import query
        info = data['evidence_files']['semantics']
        semantic_path = (folder / info['name']).resolve()
        if semantic_path.parent != folder or file_fingerprint(semantic_path)['sha256'] != info['sha256']:
            parser.error('语义证据文件路径或 SHA256 不匹配')
        semantic_doc = json.loads(semantic_path.read_text(encoding='utf-8'))
        result['semantics'] = query(semantic_doc, folder, args.start, args.end) if semantic_doc.get('duration') else semantic_doc
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'query':
        return query_main(sys.argv[2:])
    parser = argparse.ArgumentParser(description='本地音频 → 调性/和弦证据与谱面；所有 BPM 均为四分音符/分钟')
    parser.add_argument('audio', type=Path)
    parser.add_argument('-o', '--out', required=True, type=Path)
    parser.add_argument('--mode', choices=['reduction', 'full'], default='reduction')
    parser.add_argument('--staves', choices=['auto', '1', '2'], default='auto')
    parser.add_argument('--separate', action='store_true')
    parser.add_argument('--stems', default='other')
    parser.add_argument('--bpm', type=float, help='四分音符/分钟；6/8 若给的是附点四分音符 BPM，需先乘 1.5')
    parser.add_argument('--ts', help='用户指定拍号；省略使用 4/4 并标注为默认值')
    parser.add_argument('--bar-offset', type=float, default=0.0,
                        help='第一个完整小节起点，原音频秒数；之前事件保留在证据中，但不写入谱面')
    parser.add_argument('--analysis-only', action='store_true', help='只生成分析与证据，不排谱')
    parser.add_argument('--semantics', action='store_true', help='额外分析原始混音的风格、类型与情感候选')
    parser.add_argument('--semantics-only', action='store_true', help='只做语义分析，跳过转录、分离与排谱')
    parser.add_argument('--models-dir', type=Path, help='本地语义权重目录；不自动下载')
    parser.add_argument('--semantics-cache', type=Path, help='显式启用本地语义分数缓存')
    parser.add_argument('--title')
    args = parser.parse_args()
    if not args.audio.is_file():
        parser.error('输入音频文件不存在')
    if args.semantics_only and args.separate:
        parser.error('semantics-only 直接分析原始混音，不能同时请求 separate')
    if args.bpm is not None and (not math.isfinite(args.bpm) or args.bpm <= 0):
        parser.error('BPM 必须为有限正数，单位为四分音符/分钟')
    if not math.isfinite(args.bar_offset) or args.bar_offset < 0:
        parser.error('bar-offset 必须为有限非负秒数')
    try:
        ts = tuple(int(x) for x in (args.ts or '4/4').split('/'))
        if len(ts) != 2 or not 1 <= ts[0] <= 64 or ts[1] not in (1, 2, 4, 8, 16, 32, 64):
            raise ValueError
    except ValueError:
        parser.error('拍号格式应为 分子/分母；分子 1..64，分母为 1/2/4/8/16/32/64')
    wanted = [stem.strip() for stem in args.stems.split(',') if stem.strip()]
    if args.separate and (not wanted or len(set(wanted)) != len(wanted) or
                          any(stem not in ('other', 'bass', 'vocals', 'drums') for stem in wanted)):
        parser.error('stems 应为不重复的 other,bass,vocals,drums 中的一项或多项')
    out = args.out
    if out.exists() and any(out.iterdir()):
        parser.error('输出目录非空，请指定新目录，避免将旧谱面误当成本次产物')
    out.mkdir(parents=True, exist_ok=True)
    if args.semantics_only:
        from music_semantics import analyze, compact
        doc = analyze(args.audio, out, args.models_dir, args.semantics_cache)
        write_json(out / 'summary.json', compact(doc))
        print(json.dumps(compact(doc), ensure_ascii=False, allow_nan=False))
        return 4 if doc['status'] == 'unavailable' else 0
    started = time.perf_counter()
    timings = {}
    audio_path = ensure_decodable(args.audio, out)
    y, sr = load_audio(audio_path)
    dur = len(y) / sr
    if not dur or args.bar_offset >= dur:
        parser.error('音频为空，或 bar-offset 不小于音频时长')
    timings['decode'] = time.perf_counter() - started
    signal_rms = float(np.sqrt(np.mean(y.astype(float) ** 2)))
    print(f'[1/6] 音频 {dur:.2f}s @ {sr}Hz', flush=True)
    step_start = time.perf_counter()
    print('[2/6] Basic Pitch 转录中...', flush=True)
    sep_info = None
    if args.separate:
        sep_info, events = run_separation(audio_path, out / 'stems', args.stems)
        events_to_midi(events, out / 'transcription.mid')
    else:
        events, midi = transcribe(audio_path)
        midi.write(str(out / 'transcription.mid'))
    timings['transcribe_and_optional_separation'] = time.perf_counter() - step_start
    step_start = time.perf_counter()
    chroma = chroma_profile(y, sr) if signal_rms > 1e-7 and dur >= 0.1 else np.zeros(12)
    d_note, d_bass = pc_hist(events), bass_hist(events)
    bpm = args.bpm if args.bpm is not None else (estimate_tempo(y, sr) if signal_rms > 1e-7 else 120.0)
    bpm_source = 'user' if args.bpm is not None else ('estimated' if signal_rms > 1e-7 else 'fallback_for_empty_signal')
    bar = bar_seconds(bpm, ts)
    chords = chord_segments(events, dur, spans=bar_spans(dur, bpm, ts, args.bar_offset))
    func = functional_scores(chords)
    fused = fuse(d_note, d_bass, chroma, func)
    tables = dict(zip(SOURCE_NAMES, [key_table(d_note), key_table(d_bass), key_table(chroma), func]))
    best, solo, consensus = select_key(fused, tables)
    decision = evaluate_decision(best, fused, consensus, events, signal_rms)
    if decision['status'] == 'insufficient_evidence':
        best = None
    decision['selected'] = key_record(best)
    decision['selection_method'] = 'three_vote_safeguard' if consensus['corrected'] else 'weighted_fusion'
    conf = confidence(fused)
    order = sorted(fused, key=lambda k: -fused[k]) if has_scores(fused) else []
    print(f'[3/6] {key_label(best)}；状态 {decision["status"]}', flush=True)
    wks = window_keys(events, dur)
    segs = segments(wks) if best is not None else []
    stability = key_stability(fused, d_note, d_bass, chroma, func, wks,
                              selected_key=best, evidence_sufficient=best is not None)
    describe_chords(chords, segs, best)
    timings['analysis'] = time.perf_counter() - step_start
    print(f'[4/6] {len(segs)} 个调性片段；{len(chords)} 个和弦片段（含未判定）', flush=True)
    qn = quantize(events, bpm, origin=args.bar_offset)
    staff_info = resolve_staves(qn, args.staves)
    statistics = score_counts(qn, staff_info, args.mode)
    statistics['events_before_score_origin'] = sum(e[1] <= args.bar_offset for e in events)
    statistics['events_clipped_at_score_origin'] = sum(e[0] < args.bar_offset < e[1] for e in events)
    artifacts = {'midi': {'status': 'written', 'name': 'transcription.mid'},
                 'musicxml': {'status': 'skipped'}, 'svg': {'status': 'skipped', 'pages': 0}}
    svgs = []
    step_start = time.perf_counter()
    if qn and not args.analysis_only:
        try:
            sc = build_score(qn, bpm, best[0] if best else None, best[1] if best else None,
                             args.mode, ts, segs=segs, staves=args.staves, origin=args.bar_offset)
            write_score_musicxml(sc, out / 'score.musicxml')
            artifacts['musicxml'] = {'status': 'written', 'name': 'score.musicxml'}
            try:
                svgs = render_svg(out / 'score.musicxml', out)
                artifacts['svg'] = {'status': 'written' if svgs else 'failed', 'pages': len(svgs)}
            except Exception as exc:
                artifacts['svg'] = {'status': 'failed', 'pages': 0, 'error': str(exc)}
        except Exception as exc:
            artifacts['musicxml'] = {'status': 'failed', 'error': str(exc)}
    else:
        reason = 'analysis_only_requested' if args.analysis_only else 'no_quantized_notes'
        artifacts['musicxml']['reason'] = reason
        artifacts['svg']['reason'] = reason
    timings['score_and_svg'] = time.perf_counter() - step_start
    print(f'[5/6] MusicXML {artifacts["musicxml"]["status"]}；SVG {len(svgs)} 页', flush=True)
    event_document = {'schema_version': SCHEMA_VERSION, 'time_unit': 'seconds',
        'time_reference': 'original_input_start', 'midi_convention': 'C4=60, A4=69',
        'amplitude_kind': 'basic_pitch_activation_not_probability_or_calibrated_loudness',
        'source': {'kind': 'basic_pitch', 'stems': wanted if args.separate else None,
                   'per_event_stem_attribution': False},
        'events': [{'id': f'e{i:06d}', 't0': float(s), 't1': float(e), 'midi': int(p),
                    'pitch_class': int(p % 12), 'activation': float(a)}
                   for i, (s, e, p, a) in enumerate(events)]}
    write_json(out / 'events.json', event_document)
    warnings_list = ['音符、低音、和弦共用转录，四路一致不是四份独立确认。',
                     '分数份额、模板拟合分数和两项一致性诊断均不是正确概率。',
                     '调性状态规则未做真实数据校准；未检测无调性、乐器身份、歌词、曲名或情绪。',
                     '速度为单一全局估计，量化为 1/16；散板、变速、三连音和摆动节奏可能失真。',
                     '转调窗口为 12 秒/3 秒；边界近似，真实误差范围尚未标定。']
    if args.ts is None:
        warnings_list.insert(0, '拍号 4/4 是默认值，不是检测结果；小节线和逐小节和弦可能错位。')
    if bpm_source != 'user':
        warnings_list.append('速度未由用户确认；估计仍使用原版 60–180 的半速/倍速归一规则。')
    if args.bar_offset:
        warnings_list.append(f'谱面从原音频 {args.bar_offset} 秒开始；之前音符仅保留在原始事件和 MIDI 中，未自动处理弱起。')
    if decision['status'] != 'candidate':
        warnings_list.append('调性存在歧义或证据不足；请结合候选与支撑信息核查。')
    for artifact_name, artifact in artifacts.items():
        if artifact['status'] == 'failed':
            warnings_list.append(f'{artifact_name} 生成失败：{artifact.get("error", "排版器未返回页面")}')
    coverage = {'total_segments': len(chords), 'labeled_segments': sum(c['root'] is not None for c in chords),
                'duration_ratio': sum(c['t1'] - c['t0'] for c in chords if c['root'] is not None) / dur}
    versions = {}
    for package in ('basic-pitch', 'librosa', 'music21', 'verovio', 'onnxruntime', 'numpy'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    from basic_pitch import ICASSP_2022_MODEL_PATH
    model_path = Path(ICASSP_2022_MODEL_PATH)
    data = {'schema_version': SCHEMA_VERSION, 'tool_version': VERSION, 'title': args.title or args.audio.stem,
        'duration': dur, 'bpm': bpm, 'bpm_source': bpm_source, 'bpm_unit': 'quarter_notes_per_minute',
        'ts': f'{ts[0]}/{ts[1]}', 'ts_source': 'user' if args.ts else 'default',
        'bar_seconds': bar, 'bar_origin_seconds': args.bar_offset,
        'bar_origin_source': 'user' if args.bar_offset else 'assumed_audio_start',
        'notes': len(events), 'key': key_label(best) if best else None, 'key_decision': decision,
        'confidence': round(float(conf[best]), 4) if best else None,
        'ranking_share': round(float(conf[best]), 4) if best else None,
        'confidence_kind': 'uncalibrated_softmax_relative_share',
        'compatibility_note': 'confidence/top.conf 为旧字段别名，非概率；key 使用等音规范拼写；stability 从三项改为两项。',
        'top': [{'key': key_label(k), 'tonic_pc': k[0], 'mode': k[1],
                 'score': round(float(fused[k]), 3), 'conf': round(float(conf[k]), 4)} for k in order[:6]],
        'solo': {name: key_label(k) if k else None for name, k in solo.items()},
        'consensus': consensus, 'stability': stability,
        'segments': [{'id': f's{i:04d}', 't0': s['t0'], 't1': s['t1'], 'key': key_label(s['key']),
                      'tonic_pc': s['key'][0], 'mode': s['key'][1], 'support_windows': s['n'],
                      'status': 'window_candidate'} for i, s in enumerate(segs)],
        'chords': chords, 'chord_coverage': coverage,
        'split_pitch': statistics['split_pitch'], 'staves': staff_info['n_staves'],
        'staves_reason': staff_info['reason'], 'poly_ratio': staff_info['poly_ratio'],
        'pitch_span': staff_info['pitch_span'], 'score_mode': args.mode, 'score_statistics': statistics,
        'separation': sep_info, 'artifacts': artifacts, 'warnings': warnings_list,
        'provenance': {'input': dict(file_fingerprint(args.audio), path=str(args.audio.resolve())),
            'decoded_input': file_fingerprint(audio_path), 'code': file_fingerprint(Path(__file__)),
            'model': dict(file_fingerprint(model_path), serialization=model_path.suffix) if model_path.is_file()
                     else {'path': str(model_path), 'sha256': None, 'note': 'runtime model is not a single file'},
            'python': sys.version, 'packages': versions, 'analysis_sample_rate': sr,
            'transcription_parameters': dict(TRANSCRIPTION_PARAMETERS, minimum_note_length_unit='milliseconds'),
            'fusion_weights': [0.30, 0.18, 0.15, 0.37], 'softmax_tau': 0.18,
            'chord_gate': {'min_events': 3, 'min_distinct_pc': 2, 'present_weight_min': 0.04,
                           'seventh_weight_min': 0.12, 'seventh_min_present': 3},
            'source_dependency_groups': {'transcription': ['音符', '低音', '和弦'], 'waveform': ['色度']},
            'external_network': 'Optional Demucs downloads disabled in this copy; semantic branch uses local files only'},
        'evidence_files': {'events': file_fingerprint(out / 'events.json')}, 'timings_seconds': timings}
    if args.semantics:
        from music_semantics import analyze, compact, unavailable, render_html
        print('[语义] 本地CPU分析原始混音...', flush=True)
        step_start = time.perf_counter()
        try:
            semantic_doc = analyze(args.audio, out, args.models_dir, args.semantics_cache)
        except (OSError, ValueError, RuntimeError, ImportError) as exc:
            semantic_doc = unavailable(exc)
            write_json(out / 'semantics.json', semantic_doc)
            render_html(semantic_doc, out)
        data['semantics'] = compact(semantic_doc)
        data['evidence_files']['semantics'] = file_fingerprint(out / 'semantics.json')
        timings['semantics'] = time.perf_counter() - step_start
        if semantic_doc['status'] == 'unavailable':
            warnings_list.append('语义分析 unavailable：' + semantic_doc['reason'])
        elif semantic_doc.get('music_presence', {}).get('status') not in ('music','mixed'):
            warnings_list.append('语义门控未获得足够音乐证据；转录、调性或谱面不能作为音乐存在性的证明。')
        warnings_list[:] = [w.replace('未检测无调性、乐器身份、歌词、曲名或情绪。', '未检测无调性、乐器身份、歌词或曲名；情绪请另看语义分支的状态与限制。') for w in warnings_list]
    timings['total_before_report'] = time.perf_counter() - started
    write_json(out / 'report.json', data)
    write_json(out / 'summary.json', make_summary(data))
    render_report(data, svgs, out)
    print(f'[6/6] 完成 -> {out / "report.html"}', flush=True)
    print(json.dumps(make_summary(data), ensure_ascii=False, allow_nan=False))
    return 3 if any(artifact['status'] == 'failed' for artifact in artifacts.values()) else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'[error] {exc}', file=sys.stderr)
        sys.exit(2)
