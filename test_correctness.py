"""Targeted contract checks; synthetic cases do not establish real-music accuracy."""
import contextlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import music_scribe as ms


class CorrectnessTests(unittest.TestCase):
    def test_meter_denominators_and_bpm_contract(self):
        for ts, expected in [((4, 4), 2), ((3, 4), 1.5), ((6, 8), 1.5), ((2, 2), 2)]:
            self.assertEqual(ms.bar_seconds(120, ts), expected)
        for bpm in [0, -2, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                ms.bar_seconds(bpm, (4, 4))

    def test_bar_spans_exact_coverage_with_manual_origin(self):
        spans = ms.bar_spans(5, 120, (6, 8), .5)
        self.assertEqual(spans, [(0, .5), (.5, 2), (2, 3.5), (3.5, 5)])
        self.assertAlmostEqual(sum(b - a for a, b in spans), 5)

    def test_no_evidence_is_not_c_major_or_stable(self):
        z = np.zeros(12)
        func = ms.functional_scores([])
        fused = ms.fuse(z, z, z, func)
        best, solo, consensus = ms.select_key(fused, dict(zip(ms.SOURCE_NAMES, [ms.key_table(z)] * 3 + [func])))
        self.assertIsNone(best)
        self.assertTrue(all(x is None for x in solo.values()))
        self.assertEqual(consensus['agree'], 0)
        checks = ms.key_stability(fused, z, z, z, func, [], evidence_sufficient=False)
        self.assertEqual((checks['passed'], checks['total']), (0, 2))
        self.assertNotIn('passed', checks['tau_sweep'])

    def test_uninformative_path_excluded(self):
        z = np.zeros(12)
        profile = np.zeros(12)
        profile[[0, 4, 7]] = [3, 2, 1]
        tab = ms.key_table(profile)
        best, solo, consensus = ms.select_key(tab, {'音符': ms.key_table(z), '色度': tab})
        self.assertIsNotNone(best)
        self.assertIsNone(solo['音符'])
        self.assertEqual(consensus['available'], 1)

    def test_majority_safeguard_and_relative_key_exception(self):
        def table(winner):
            return {k: float(k == winner) for k in ms.key_table(np.zeros(12))}
        c, d, a_minor = (0, 'major'), (2, 'major'), (9, 'minor')
        paths = {'音符': table(c), '低音': table(c), '色度': table(c), '和弦': table(d)}
        best, _, consensus = ms.select_key(table(d), paths)
        self.assertEqual(best, c)
        self.assertTrue(consensus['corrected'])
        best, _, consensus = ms.select_key(table(a_minor), paths)
        self.assertEqual(best, a_minor)
        self.assertFalse(consensus['corrected'])

    def test_safeguard_reference_is_final_decision(self):
        z = np.zeros(12)
        profile = np.array(ms.KK_MAJOR)
        fused = ms.fuse(profile, profile, profile, ms.functional_scores([]))
        checks = ms.key_stability(fused, profile, profile, profile, ms.functional_scores([]), [],
                                  selected_key=(2, 'minor'))
        self.assertEqual(checks['reference_key']['tonic_pc'], 2)
        self.assertEqual(checks['reference_key']['mode'], 'minor')

    def test_decision_status_not_probability(self):
        table = ms.key_table(np.array(ms.KK_MAJOR))
        decision = ms.evaluate_decision((0, 'major'), table, {'agree': 4, 'available': 4, 'corrected': False},
                                        [(0, 1, 60, .5)] * 2, .1)
        self.assertEqual(decision['status'], 'insufficient_evidence')
        self.assertFalse(decision['calibrated'])

    def test_all_chromatic_roman_degrees_in_c(self):
        expected = ['I', '♭II', 'II', '♭III', 'III', 'IV', '♭V', 'V', '♭VI', 'VI', '♭VII', 'VII']
        self.assertEqual([ms.roman({'root': pc, 'q': ''}, 0, 'major') for pc in range(12)], expected)
        self.assertEqual(ms.roman({'root': 1, 'q': 'm7'}, 0, 'major'), '♭ii7')

    def test_enharmonic_keys_have_conventional_signature(self):
        from music21 import key
        for mode in ['major', 'minor']:
            for pc in range(12):
                k = key.Key(ms.KEY_SPELLINGS[mode][pc], mode)
                self.assertEqual(k.tonic.pitchClass, pc)
                self.assertLessEqual(abs(k.sharps), 6)
        self.assertEqual(key.Key(ms.KEY_SPELLINGS['major'][10], 'major').sharps, -2)

    def test_chord_unknown_spans_and_ids_retained(self):
        events = [(0, 1, 60, .8), (0, 1, 64, .8), (0, 1, 67, .8)]
        chords = ms.chord_segments(events, 2, spans=[(0, 1), (1, 2)])
        self.assertEqual(len(chords), 2)
        self.assertEqual(chords[0]['support_count'], 3)
        self.assertEqual(set(chords[0]['support_event_ids']), {'e000000', 'e000001', 'e000002'})
        self.assertIsNone(chords[1]['root'])
        self.assertEqual(chords[1]['reason'], 'fewer_than_three_events')

    def test_seventh_gate_not_relaxed(self):
        events = [(0, 1, p, .8) for p in [55, 57, 67, 69]]
        c = ms.chord_segments(events, 1)[0]
        self.assertNotIn(c['q'], ('maj7', 'm7', '7', 'm7b5'))
        for pc in c['supported_pitch_classes']:
            self.assertIn(pc, c['detected_pitch_classes'])

    def test_repeated_one_pitch_not_harmony(self):
        c = ms.chord_segments([(0, 1, 60, .8)] * 4, 1)[0]
        self.assertIsNone(c['root'])
        self.assertEqual(c['reason'], 'fewer_than_two_pitch_classes')

    def test_roman_uses_local_segment_and_marks_boundary(self):
        c = ms.chord_segments([(0, 2, p, .8) for p in [62, 66, 69]], 2)[0]
        segs = [{'t0': 0, 't1': .5, 'key': (0, 'major')}, {'t0': .5, 't1': 2, 'key': (2, 'major')}]
        ms.describe_chords([c], segs, (0, 'major'))
        self.assertEqual(c['roman'], 'I')
        self.assertEqual(c['key_basis']['segment_id'], 's0001')
        self.assertTrue(c['crosses_key_boundary'])

    def test_merge_across_bin_boundary(self):
        events = ms.merge_events([(.0149, 1, 60, .8)], [(.0151, 1.2, 60, .9)])
        self.assertEqual(events, [(.0151, 1.2, 60, .9)])

    def test_merge_does_not_chain_or_merge_different_pitches(self):
        events = ms.merge_events([(0, 1, 60, .5), (.025, 1, 60, .8), (.05, 1, 60, .9), (0, 1, 61, .9)])
        self.assertEqual(len(events), 3)
        for tol in [0, float('inf')]:
            with self.assertRaises(ValueError):
                ms.merge_events([], tol=tol)

    def test_origin_crop_is_explicit_and_long_duration_preserved(self):
        qn = ms.quantize([(0, .25, 60, .5), (.25, 1, 62, .6), (1, 20, 64, .7)], 120, origin=.5)
        self.assertEqual(len(qn), 2)
        self.assertEqual(qn[0]['o'], 0)
        self.assertEqual(qn[0]['d'], 1)
        self.assertEqual(qn[1]['d'], 38)

    def test_duration_lane_intervals_do_not_overlap(self):
        items = [{'o': 0, 'd': 2, 'p': 60, 'a': .9}, {'o': 0, 'd': .25, 'p': 64, 'a': .8},
                 {'o': .5, 'd': .25, 'p': 67, 'a': .7}]
        lanes = ms.duration_lanes(items)
        self.assertEqual(sum(map(len, lanes)), len(items))
        self.assertTrue(all(a['o'] + a['d'] <= b['o'] for lane in lanes for a, b in zip(lane, lane[1:])))

    def test_full_musicxml_roundtrip_preserves_independent_durations(self):
        from music21 import converter
        items = [{'o': 0., 'd': 2., 'p': 60, 'a': .9}, {'o': 0., 'd': .25, 'p': 64, 'a': .8},
                 {'o': .5, 'd': .25, 'p': 67, 'a': .7}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'score.musicxml'
            ms.build_score(items, 120, 0, 'major', 'full', staves='1').write('musicxml', fp=str(path))
            score = converter.parse(str(path)).stripTies()
            actual = sorted((float(n.getOffsetInHierarchy(score)), n.pitch.midi, float(n.duration.quarterLength))
                            for n in score.recurse().notes)
        self.assertEqual(actual, [(0, 60, 2), (0, 64, .25), (.5, 67, .25)])

    def test_full_no_six_note_cap_and_bflat_musicxml(self):
        import xml.etree.ElementTree as ET
        notes = [{'o': 0., 'd': 1., 'p': p, 'a': .8} for p in range(60, 69)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'score.musicxml'
            ms.build_score(notes, 120, 10, 'major', 'full', staves='1').write('musicxml', fp=str(path))
            xml = ET.parse(path)
        self.assertEqual(len(xml.findall('.//pitch')), 9)
        self.assertEqual({int(x.text) for x in xml.findall('.//fifths')}, {-2})

    def test_polyphonic_cross_bar_ties_with_repeated_pitches(self):
        from verify_musicxml import read_intervals
        import collections
        items = [{'o': o, 'd': d, 'p': p, 'a': .8} for o, d, p in
                 [(2.25, 1.5, 71), (3.5, .75, 76), (3.75, .75, 71),
                  (3.75, .5, 81), (3.75, .5, 83), (4.75, .5, 71), (10.75, 1.5, 71)]]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'score.musicxml'
            ms.build_score(items, 120, 4, 'minor', 'full', staves='1').write('musicxml', fp=str(path))
            actual, stats = read_intervals(path)
        expected = collections.Counter((n['p'], n['o'], n['d']) for n in items)
        self.assertEqual(actual, expected)
        self.assertGreater(stats['tied_continuation_segments'], 0)

    def test_xml_verifier_rejects_unmatched_tie(self):
        from verify_musicxml import read_intervals
        fixture = '''<score-partwise><part><measure><attributes><divisions>4</divisions></attributes>
        <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration>
        <tie type="stop"/><voice>1</voice></note></measure></part></score-partwise>'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.musicxml'
            path.write_text(fixture, encoding='utf-8')
            with self.assertRaises(ValueError):
                read_intervals(path)

    def test_six_eight_key_change_matches_seconds(self):
        from music21 import stream, key
        notes = [{'o': float(i), 'd': 1., 'p': 60, 'a': .8} for i in range(9)]
        score = ms.build_score(notes, 120, 0, 'major', ts=(6, 8), staves='1',
                              segs=[{'t0': 1.5, 't1': 4.5, 'key': (2, 'major'), 'n': 2}])
        changes = [(measure.number, k.sharps) for measure in score.parts[0].getElementsByClass(stream.Measure)
                   for k in measure.getElementsByClass(key.Key)]
        self.assertIn((2, 2), changes)

    def test_split_pitch_reports_actual_clamped_value(self):
        notes = [{'o': float(i), 'd': 1, 'p': 30 + i, 'a': .7} for i in range(10)]
        metrics = ms.resolve_staves(notes, '2')
        self.assertEqual(ms.score_counts(notes, metrics, 'full')['split_pitch'], 48)

    def test_query_overlap_limit_and_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            event_file = folder / 'events.json'
            ms.write_json(event_file, {'events': [{'id': 'e000000', 't0': .5, 't1': 1.5}]})
            report = folder / 'report.json'
            ms.write_json(report, {'schema_version': ms.SCHEMA_VERSION, 'duration': 2, 'warnings': [],
                'key_decision': {'status': 'ambiguous'}, 'chords': [], 'segments': [],
                'provenance': {'input': {'sha256': 'fixture'}},
                'evidence_files': {'events': ms.file_fingerprint(event_file)}})
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                ms.query_main([str(report), '--start', '1', '--end', '1.25', '--notes-limit', '1'])
            data = json.loads(output.getvalue())
            self.assertEqual(data['note_count_total'], 1)
            self.assertFalse(data['notes_truncated'])
            event_file.write_text('{}', encoding='utf-8')
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                ms.query_main([str(report), '--start', '1', '--end', '1.25'])
            self.assertEqual(caught.exception.code, 2)

    def test_bad_arguments_fail_before_inference(self):
        for args in [['missing.wav', '-o', 'unused'],
                     [str(Path(__file__)), '-o', 'unused', '--bpm', 'nan'],
                     [str(Path(__file__)), '-o', 'unused', '--ts', '6/3'],
                     [str(Path(__file__)), '-o', 'unused', '--bar-offset', '-1']]:
            result = subprocess.run([sys.executable, str(Path(ms.__file__)), *args], capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(b'Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
