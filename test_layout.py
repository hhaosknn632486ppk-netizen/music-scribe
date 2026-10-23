"""Notation invariants and independently parsed beam/rest failure cases."""
from collections import Counter
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import music_scribe as ms
from verify_layout import inspect_layout
from verify_musicxml import read_intervals


class LayoutTests(unittest.TestCase):
    def export(self, intervals, mode='full', ts=(4, 4), staves='1'):
        items = [dict(o=o, d=d, p=p, a=.7) for o, d, p in intervals]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'score.musicxml'
            ms.write_score_musicxml(ms.build_score(items, 120, 0, 'major', mode,
                                                   ts=ts, staves=staves), path)
            actual, _ = read_intervals(path)
            metrics = inspect_layout(path, check_staff_rests=True)['metrics']
            root = ET.parse(path).getroot()
        if mode == 'full':
            self.assertEqual(actual, Counter((p, o, d) for o, d, p in intervals))
        return actual, metrics, root

    def test_chords_share_only_equal_onset_and_duration(self):
        _, metrics, _ = self.export([(0, 1, 60), (0, 1, 64), (0, .5, 67), (0, 1, 60)])
        self.assertGreater(metrics['chord_members'], 0)
        self.assertEqual(metrics['maximum_pitched_voices_per_staff_measure'], 3)

    def test_hidden_spacers_preserve_true_staff_silence(self):
        _, metrics, root = self.export([(1, 1, 60), (1.25, .25, 72), (3, .5, 64)])
        self.assertGreater(metrics['hidden_rests'], 0)
        self.assertGreater(metrics['visible_rests'], 0)
        self.assertEqual(metrics['visible_rest_note_overlaps'], 0)
        self.assertTrue(all(n.get('print-object') != 'no' for n in root.findall('.//note') if n.find('pitch') is not None))

    def test_actual_gaps_break_beams_but_contiguous_notes_are_beamed(self):
        _, metrics, root = self.export([(0, .25, 60), (.5, .25, 62), (.75, .25, 64), (1, .25, 65)])
        pitched = [n for n in root.findall('.//note') if n.find('pitch') is not None]
        self.assertIsNone(pitched[0].find('beam'))
        self.assertEqual(pitched[1].findtext('beam'), 'begin')
        self.assertEqual(pitched[2].findtext('beam'), 'end')
        self.assertIsNone(pitched[3].find('beam'))
        self.assertGreater(metrics['beam_elements'], 0)

    def test_mixed_lengths_generate_inward_hooks(self):
        _, metrics, root = self.export([(0, .25, 60), (.25, .5, 62), (.75, .25, 64)])
        hooks = [b.text for b in root.findall('.//beam') if 'hook' in b.text]
        self.assertEqual(hooks, ['forward hook', 'backward hook'])
        self.assertEqual(metrics['primary_beam_groups'], 1)

    def test_compound_meter_keeps_two_dotted_quarter_beats(self):
        _, metrics, _ = self.export([(i / 2, .5, 60 + i) for i in range(6)], ts=(6, 8))
        self.assertEqual(metrics['primary_beam_groups'], 2)

    def test_cross_bar_chords_keep_individual_note_intervals(self):
        _, metrics, _ = self.export([(3.75, 8.5, 60), (3.75, 8.5, 64), (3.75, 8.5, 60),
                                   (4, 1.25, 72)], staves='2')
        self.assertGreater(metrics['chord_members'], 0)

    def test_reduction_keeps_its_previous_simplification_contract(self):
        actual, _, _ = self.export([(0, 1, 60), (0, .5, 64), (2, .5, 67)], mode='reduction')
        self.assertEqual(actual, Counter([(60, 0., 1.), (64, 0., 1.), (67, 2., .5)]))

    def test_validator_rejects_orphan_open_beam_and_wrong_hook(self):
        _, _, good = self.export([(0, .25, 60), (.25, .5, 62), (.75, .25, 64)])
        for corruption in ['missing_begin', 'missing_end', 'wrong_hook', 'hide_note']:
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as tmp:
                root = ET.fromstring(ET.tostring(good))
                pitched = [n for n in root.findall('.//note') if n.find('pitch') is not None]
                if corruption == 'missing_begin':
                    pitched[0].remove(pitched[0].find("beam[@number='1']"))
                elif corruption == 'missing_end':
                    pitched[-1].find("beam[@number='1']").text = 'continue'
                elif corruption == 'wrong_hook':
                    pitched[0].find("beam[@number='2']").text = 'backward hook'
                else:
                    pitched[0].set('print-object', 'no')
                path = Path(tmp) / 'bad.musicxml'
                ET.ElementTree(root).write(path)
                with self.assertRaises(ValueError):
                    inspect_layout(path, check_staff_rests=True)


if __name__ == '__main__':
    unittest.main()
