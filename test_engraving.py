"""Visible accidental meaning and interval-preserving notation regressions."""
from collections import Counter
from pathlib import Path
import tempfile
import random
import unittest
import xml.etree.ElementTree as ET
from music21 import stream, note, key, tie
import music_scribe as ms
from verify_engraving import verify
from verify_musicxml import read_intervals


class EngravingTests(unittest.TestCase):
    def part(self, voices, fifths=0):
        part = stream.Part()
        m = stream.Measure(number=1)
        m.insert(0, key.KeySignature(fifths))
        for i, members in enumerate(voices):
            voice = stream.Voice(id=i+1)
            for offset, name in members:
                voice.insert(offset, note.Note(name, quarterLength=.5))
            m.insert(0, voice)
        part.append(m)
        ms._engrave_accidentals(part)
        return part

    def test_key_accidentals_and_restoring_naturals(self):
        p = self.part([[(0, 'F#4'), (1, 'F4'), (2, 'F4'), (3, 'F#4')]], 1)
        self.assertEqual([n.pitch.accidental.displayStatus for n in p.recurse().notes], [False, True, False, True])

    def test_shared_state_across_voices(self):
        p = self.part([[(0, 'C#4')], [(1, 'C#4'), (2, 'C4')]])
        self.assertEqual([n.pitch.accidental.displayStatus for n in p.recurse().notes], [True, False, True])

    def test_simultaneous_conflict_and_next_attack_are_explicit(self):
        p = self.part([[(0, 'C#4'), (1, 'C4')], [(0, 'C4')]])
        self.assertTrue(all(n.pitch.accidental.displayStatus for n in p.recurse().notes))

    def test_duplicate_same_pitch_shares_one_symbol(self):
        p = self.part([[(0, 'B-4')], [(0, 'B-4')]])
        self.assertEqual(sum(n.pitch.accidental.displayStatus for n in p.recurse().notes), 1)

    def test_octaves_and_parts_have_separate_state(self):
        p = self.part([[(0, 'C#4'), (1, 'C#5')]])
        q = self.part([[(0, 'C#4')]])
        self.assertTrue(all(n.pitch.accidental.displayStatus for n in [*p.recurse().notes, *q.recurse().notes]))

    def test_new_measure_resets_state(self):
        p = self.part([[(0, 'C#4')]])
        m = stream.Measure(number=2); m.append(note.Note('C#4'))
        p.append(m); ms._engrave_accidentals(p)
        self.assertTrue(m.notes[0].pitch.accidental.displayStatus)

    def test_tie_continuation_does_not_set_next_attack(self):
        p = stream.Part(); m = stream.Measure(number=1)
        a = note.Note('C#4'); a.tie = tie.Tie('stop')
        b = note.Note('C#4'); m.append([a, b]); p.append(m)
        ms._engrave_accidentals(p)
        self.assertFalse(a.pitch.accidental.displayStatus)
        self.assertTrue(b.pitch.accidental.displayStatus)

    def test_full_export_keeps_intervals_and_tie_sides(self):
        items = [(3.75, 8.5, 61), (3.75, 8.5, 65), (4, .25, 72), (5, .5, 60)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'score.musicxml'
            sc = ms.build_score([dict(o=o,d=d,p=p,a=.8) for o,d,p in items],120,0,'major','full')
            ms.write_score_musicxml(sc,path)
            self.assertEqual(read_intervals(path)[0],Counter((p,o,d) for o,d,p in items))
            self.assertEqual(verify(path)['status'],'PASS')
            root=ET.parse(path)
            # music21 emits a continue as stop + start; its stop half has no
            # placement attribute. Every outgoing arc carries the chain side.
            arcs = root.findall('.//notations/tied[@type="start"]')
            self.assertTrue(arcs)
            self.assertTrue(all(t.get('placement') in ('above','below') for t in arcs))

    def test_validator_rejects_missing_and_wrong_accidental(self):
        xml = '<score-partwise><part><measure number="1"><attributes><divisions>1</divisions></attributes><note><pitch><step>C</step><alter>1</alter><octave>4</octave></pitch><duration>1</duration>{}</note></measure></part></score-partwise>'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'score.musicxml'
            for value in ('','<accidental>flat</accidental>'):
                path.write_text(xml.format(value))
                with self.assertRaises(ValueError): verify(path)
            path.write_text(xml.format('<accidental>sharp</accidental>'))
            self.assertEqual(verify(path)['status'],'PASS')

    def test_random_polyphony_accidentals_preserve_intervals(self):
        rng = random.Random(133)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'score.musicxml'
            for _ in range(15):
                items = [(rng.randrange(48)/4, rng.randrange(1,25)/4, rng.randrange(45,85)) for _ in range(25)]
                sc=ms.build_score([dict(o=o,d=d,p=p,a=.8) for o,d,p in items],120,rng.randrange(12),'major','full')
                ms.write_score_musicxml(sc,path)
                self.assertEqual(verify(path)['status'],'PASS')
                self.assertEqual(read_intervals(path)[0],Counter((p,o,d) for o,d,p in items))


if __name__ == '__main__': unittest.main()
