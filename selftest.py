#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selftest.py — 用已知调性的合成音频做回归测试。

合成曲目：指定调性的 I-vi-IV-V-I 进行 + 三音和弦 + 低音 + 旋律，
走完整的「Basic Pitch 转录 -> 三路定调」链路，核对是否还原出该调。

注意：合成音频比真实录音容易（单一音色、无混响、节拍严格），
这里的分数用来验证「链路没坏」，不能当作真实音乐的准确率。
"""
import sys, tempfile, numpy as np
from pathlib import Path
sys.path.insert(0, ".")
from music_scribe import (transcribe, pc_hist, bass_hist, chroma_profile,
                          key_table, fuse, confidence, chord_segments,
                          functional_scores, estimate_tempo, PC_NAMES, bar_seconds)

SR = 22050
MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]


def tone(f, dur, amp=0.3):
    t = np.arange(int(dur * SR)) / SR
    w = np.zeros_like(t)
    for k, g in ((1, 1.0), (2, 0.42), (3, 0.22), (4, 0.12), (5, 0.07)):
        w += g * np.sin(2 * np.pi * f * k * t)
    env = np.minimum(1, t / 0.012) * np.exp(-t * 1.6)
    return amp * w * env / 1.7


def midi_f(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def make_piece(root, mode, bpm=100, bars=5, sevenths=False, progression=None):
    """root: 主音 MIDI 的 pc；mode: major/minor"""
    scale = MAJOR if mode == "major" else MINOR
    deg_pc = lambda d: (root + scale[d % 7]) % 12
    # I - vi - IV - V - I （用级数）
    prog = [(0, 2, 4), (5, 0, 2), (3, 5, 0), (4, 6, 1), (0, 2, 4)]
    if sevenths:
        prog = [(0, 2, 4, 6), (5, 0, 2, 4), (3, 5, 0, 2),
                (4, 6, 1, 3), (0, 2, 4, 6)]
    if progression is not None:
        prog = progression
    beat = 60.0 / bpm
    out = np.zeros(int(bars * 4 * beat * SR) + SR)
    n = 0
    for bar in range(bars):
        triad = prog[bar % len(prog)]
        for b in range(4):
            t0 = (bar * 4 + b) * beat
            # 低音：根音（八度 2）——注意要换算成音级，不能直接用级数编号
            pcs = deg_pc(triad[0])
            m = 36 + ((pcs - 36) % 12)
            seg = tone(midi_f(m), beat * 1.05, 0.35)
            i = int(t0 * SR); out[i:i + len(seg)] += seg[:len(out) - i]
            # 和弦三音（八度 4），只在 1、3 拍
            if b % 2 == 0:
                for d in triad:
                    pc = deg_pc(d)
                    mm = 60 + ((pc - 60) % 12)
                    seg = tone(midi_f(mm), beat * 1.9, 0.16)
                    i = int(t0 * SR); out[i:i + len(seg)] += seg[:len(out) - i]
            # 旋律：级数随机
            pc = deg_pc(int(np.random.choice([0, 1, 2, 3, 4, 5, 6])))
            mm = 72 + ((pc - 72) % 12)
            seg = tone(midi_f(mm), beat * 0.9, 0.22)
            i = int(t0 * SR); out[i:i + len(seg)] += seg[:len(out) - i]
            n += 1
    out /= max(1e-6, np.abs(out).max()) / 0.9
    return out


def analyse(wav_path, bpm=None, ts=(4, 4)):
    ev, _ = transcribe(wav_path)
    import librosa
    y, _ = librosa.load(str(wav_path), sr=SR, mono=True)
    dn, db, ch = pc_hist(ev), bass_hist(ev), chroma_profile(y, SR)
    bpm = bpm or estimate_tempo(y, SR)
    bar = bar_seconds(bpm, ts)
    func = functional_scores(chord_segments(ev, len(y) / SR, win=bar, hop=bar))
    f = fuse(dn, db, ch, func)
    best = max(f, key=f.get)
    c = confidence(f)
    tabs = {"音符": key_table(dn), "低音": key_table(db),
            "色度": key_table(ch), "和弦": func}
    return best, c[best], {k: max(v, key=v.get) for k, v in tabs.items()}


def make_modulating_piece(bpm=80, bars=8):
    """Eight bars of E minor followed by eight bars of D major; fixed RNG seed."""
    state = np.random.get_state()
    try:
        np.random.seed(20261019)
        # Tonic ostinati with scale melodies keep both local tonics unambiguous.
        first = make_piece(4, "minor", bpm=bpm, bars=bars, progression=[(0, 2, 4)])
        second = make_piece(2, "major", bpm=bpm, bars=bars, progression=[(0, 2, 4)])
    finally:
        np.random.set_state(state)
    boundary_sample = round(bars * 4 * 60 / bpm * SR)
    return np.concatenate((first[:boundary_sample], second))


def test_modulation(out):
    import json
    import soundfile as sf
    import xml.etree.ElementTree as ET
    from music21 import key, stream
    from music_scribe import window_keys, segments, quantize, build_score, write_score_musicxml, KEY_WINDOW_SECONDS

    out.mkdir(parents=True, exist_ok=True)
    bpm, bars, ts = 80, 8, (4, 4)
    bar_s = bar_seconds(bpm, ts)
    boundary_s = bars * bar_s
    wav = out / "em_to_d.wav"
    y = make_modulating_piece(bpm, bars)
    sf.write(str(wav), y.astype(np.float32), SR)
    events, _ = transcribe(wav)
    windows = window_keys(events, len(y) / SR)
    segs = segments(windows)
    assert all(a['t1'] <= b['t0'] for a, b in zip(segs, segs[1:]))
    assert segs and segs[0]['key'] == (4, 'minor'), segs
    assert any(s['key'] == (2, 'major') for s in segs), segs
    score = build_score(quantize(events, bpm), bpm, 4, "minor", ts=ts, segs=segs)
    # Check every music21 part before the two piano staves are combined in MusicXML.
    part_keys = []
    for part in score.parts:
        changes = [(m.number, k.sharps, k.mode) for m in part.getElementsByClass(stream.Measure)
                   for k in m.getElementsByClass(key.Key)]
        assert changes[0] == (1, 1, 'minor'), changes
        assert any(k[1:] == (2, 'major') for k in changes), changes
        assert all(a[1:] != b[1:] for a, b in zip(changes, changes[1:])), changes
        part_keys.append(changes)
    xml = out / 'score.musicxml'
    write_score_musicxml(score, xml)
    root = ET.parse(xml).getroot()
    xml_keys = [{'part': p.attrib['id'], 'measure': int(m.attrib['number']),
                 'staff': k.get('number', 'all'), 'fifths': int(k.findtext('fifths')),
                 'mode': k.findtext('mode')}
                for p in root.findall('part') for m in p.findall('measure')
                for k in m.findall('./attributes/key')]
    fifths = sorted({k['fifths'] for k in xml_keys})
    assert {1, 2} <= set(fifths), xml_keys
    second = next(k for k in xml_keys if k['fifths'] == 2 and k['mode'] == 'major')
    detected = next(s for s in segs if s['key'] == (2, 'major'))
    expected_measure = round(detected['t0'] / bar_s) + 1
    assert second['measure'] == expected_measure, (second, detected)
    allowed = (max(1, round((boundary_s - KEY_WINDOW_SECONDS) / bar_s) + 1),
               round((boundary_s + KEY_WINDOW_SECONDS) / bar_s) + 1)
    assert allowed[0] <= second['measure'] <= allowed[1], (second, allowed)
    assert all(changes == part_keys[0] for changes in part_keys), part_keys
    metrics = {'seed': 20261019, 'bpm': bpm, 'bars_per_key': bars,
               'true_boundary_seconds': boundary_s, 'true_boundary_measure': bars + 1,
               'allowed_measure_region': allowed, 'detected_boundary_seconds': detected['t0'],
               'inserted_measure': second['measure'], 'distinct_fifths': fifths,
               'part_keys': part_keys, 'xml_keys': xml_keys, 'segments': segs,
               'notes': len(events)}
    (out / 'metrics.json').write_text(json.dumps(metrics, indent=2) + '\n', encoding='utf-8')
    # Retain exact detector inputs for before/after score-writing comparisons.
    (out / 'events.json').write_text(json.dumps(events), encoding='utf-8')
    print(f"转调 PASS: fifths={fifths}; D major measure={second['measure']}; "
          f"true boundary=measure {bars+1}; allowed={allowed}; parts={len(part_keys)}")
    return metrics


def main():
    import argparse
    import soundfile as sf
    ap = argparse.ArgumentParser()
    ap.add_argument('--modulation-only', action='store_true')
    ap.add_argument('--modulation-out', type=Path)
    args = ap.parse_args()
    cases = [(7, "major"), (2, "minor"), (0, "major"), (9, "minor"),
             (5, "major"), (11, "minor"), (4, "minor"), (10, "major")]
    tmp = Path(tempfile.mkdtemp())
    modulation_out = args.modulation_out or tmp / 'modulation'
    if args.modulation_only:
        test_modulation(modulation_out)
        return 0
    hit = {"合并": 0, "音符": 0, "低音": 0, "色度": 0, "和弦": 0}
    print(f"{'目标调':<10}{'判定':<10}{'置信':>6}  四路独立")
    for pc, mode in cases:
        np.random.seed(pc * 13 + len(mode))
        y = make_piece(pc, mode)
        fp = tmp / f"t_{pc}_{mode}.wav"
        sf.write(str(fp), y.astype(np.float32), SR)
        best, conf, solo = analyse(fp)
        target = (pc, mode)
        ok = best == target
        hit["合并"] += ok
        for k, v in solo.items():
            hit[k] += (v == target)
        nm = lambda k: f"{PC_NAMES[k[0]]} {'大' if k[1]=='major' else '小'}"
        print(f"{nm(target):<10}{nm(best):<10}{conf*100:5.1f}%  " +
              " / ".join(f"{k}:{nm(v)}" for k, v in solo.items()) +
              ("  ✓" if ok else "  ✗"))
    n = len(cases)
    print(f"\n合并判定 {hit['合并']}/{n}  音符 {hit['音符']}/{n}  "
          f"低音 {hit['低音']}/{n}  色度 {hit['色度']}/{n}  和弦 {hit['和弦']}/{n}")
    seventh_cases = [(0, "major"), (2, "minor"), (7, "major"), (4, "minor")]
    seventh_hit = 0
    for pc, mode in seventh_cases:
        np.random.seed(pc * 13 + len(mode))
        y = make_piece(pc, mode, sevenths=True)
        fp = tmp / f"seventh_{pc}_{mode}.wav"
        sf.write(str(fp), y.astype(np.float32), SR)
        best, conf, solo = analyse(fp)
        ok = best == (pc, mode)
        seventh_hit += ok
        print(f"七和弦 {PC_NAMES[pc]} {mode}: {PC_NAMES[best[0]]} {best[1]} "
              + ("✓" if ok else "✗"))
    print(f"七和弦判定 {seventh_hit}/{len(seventh_cases)}")
    test_modulation(modulation_out)
    return 0 if hit["合并"] == n and seventh_hit == len(seventh_cases) else 1


if __name__ == "__main__":
    sys.exit(main())
