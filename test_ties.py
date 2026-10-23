"""MusicXML interval and tie regressions; no claim of transcription accuracy."""
from collections import Counter
from pathlib import Path
import random
import tempfile
import unittest
import xml.etree.ElementTree as ET

import music_scribe as ms
from verify_musicxml import read_intervals
from verify_layout import inspect_layout


class TieExportTests(unittest.TestCase):
    def roundtrip(self, intervals, staves='2', ts=(4, 4)):
        items = [dict(o=o, d=d, p=p, a=.8) for o, d, p in intervals]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'score.musicxml'
            score = ms.build_score(items, 120, 0, 'major', 'full', staves=staves, ts=ts)
            ms.write_score_musicxml(score, path)
            actual, stats = read_intervals(path)
            inspect_layout(path, check_staff_rests=True)
            self.assertEqual(actual, Counter((p, o, d) for o, d, p in intervals))
            root = ET.parse(path)
            staff_voices = {}
            for n in root.findall('.//note'):
                staff = n.findtext('staff', '1')
                voice = n.findtext('voice')
                self.assertIsNotNone(voice)
                self.assertGreater(int(voice), 0)
                staff_voices.setdefault(staff, set()).add(voice)
            if len(staff_voices) == 2:
                self.assertFalse(staff_voices['1'] & staff_voices['2'])
            return stats, root

    def test_lower_tie_survives_upper_singleton_to_polyphony(self):
        stats, _ = self.roundtrip([(0, .25, 84), (4, .5, 84), (4, .5, 88), (3.75, .5, 48)])
        self.assertGreater(stats['tied_continuation_segments'], 0)

    def test_lower_tie_survives_silent_upper_measure(self):
        self.roundtrip([(0, 1, 84), (8, .5, 84), (8, .5, 88), (3.75, 5, 48)])

    def test_same_pitch_overlapping_ties_remain_separate(self):
        self.roundtrip([(3.5, 9.75, 60), (3.75, 5.5, 60), (4, 1.25, 60)], staves='1')

    def test_composite_durations_and_trailing_empty_staff(self):
        self.roundtrip([(0, 1.25, 84), (2.75, 2.5, 48), (13.75, 8.5, 48)])

    def test_non_four_four_meters(self):
        for ts in [(6, 8), (3, 4), (2, 2)]:
            with self.subTest(ts=ts):
                self.roundtrip([(0, .25, 84), (2.75, 7.5, 48), (4, .25, 84), (4, 1.25, 88)], ts=ts)

    def test_duplicate_events_and_unpitched_empty_staff(self):
        self.roundtrip([(3.75, .5, 60), (3.75, .5, 60), (8, 1.25, 60)])

    def test_seeded_sparse_polyphonic_layouts(self):
        rng = random.Random(20261023)
        for case in range(24):
            with self.subTest(case=case):
                intervals = [(rng.randrange(0, 64) / 4, rng.randrange(1, 35) / 4,
                              rng.choice([36, 48, 60, 60, 72, 84])) for _ in range(20)]
                self.roundtrip(intervals, staves='1' if case % 3 == 0 else '2',
                               ts=(6, 8) if case % 4 == 0 else (4, 4))

    def test_verifier_still_rejects_wrong_voice_staff_gaps_and_missing_stop(self):
        # Deliberately corrupt an otherwise valid cross-bar chain. No relaxed
        # pitch-only matching is allowed to conceal changed voice/staff IDs.
        _, good = self.roundtrip([(3.75, .5, 60)], staves='1')
        for mutation in ('voice', 'staff', 'gap', 'missing_stop'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = ET.fromstring(ET.tostring(good.getroot()))
                stop = next(n for n in root.findall('.//note') if n.find("tie[@type='stop']") is not None)
                if mutation in ('voice', 'staff'):
                    element = stop.find(mutation)
                    if element is None:
                        element = ET.SubElement(stop, mutation)
                    element.text = '999'
                elif mutation == 'missing_stop':
                    stop.remove(stop.find("tie[@type='stop']"))
                else:
                    measure = next(m for m in root.findall('.//measure') if stop in list(m))
                    forward = ET.Element('forward')
                    ET.SubElement(forward, 'duration').text = '1'
                    measure.insert(list(measure).index(stop), forward)
                path = Path(tmp) / 'bad.musicxml'
                ET.ElementTree(root).write(path)
                with self.assertRaises(ValueError):
                    read_intervals(path)


if __name__ == '__main__':
    unittest.main()
