"""Read visible accidentals as a player would; compare to encoded pitches.

Supplementary symbolic check, not a pixel-collision or transcription audit.
Tied continuations retain their pitch; simultaneous conflicting alterations
must be explicit. Accidental state is per staff, octave and bar.
"""
import argparse
from collections import defaultdict
from fractions import Fraction
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ACCIDENTALS = {'natural': 0, 'sharp': 1, 'flat': -1, 'double-sharp': 2,
               'sharp-sharp': 2, 'flat-flat': -2, 'natural-sharp': 1, 'natural-flat': -1}


def verify(path):
    root = ET.parse(path)
    checked, displayed, tied = 0, 0, 0
    for part in root.findall('part'):
        keys, divisions, staff_count = {}, None, 1
        for measure in part.findall('measure'):
            groups = defaultdict(list)
            cursor, previous_start = Fraction(0), Fraction(0)
            for el in measure:
                if el.tag == 'attributes':
                    divisions = int(el.findtext('divisions', str(divisions)))
                    staff_count = int(el.findtext('staves', str(staff_count)))
                    for key in el.findall('key'):
                        fifths = int(key.findtext('fifths', '0'))
                        if abs(fifths) > 7:
                            raise ValueError('Unsupported nonstandard key signature')
                        alters = {s: (1 if fifths > 0 else -1) for s in
                                  ('FCGDAEB' if fifths > 0 else 'BEADGCF')[:abs(fifths)]}
                        targets = [key.get('number')] if key.get('number') else [str(i + 1) for i in range(staff_count)]
                        for staff in targets:
                            keys[staff] = alters
                elif el.tag in ('backup', 'forward'):
                    cursor += Fraction(int(el.findtext('duration')), divisions) * (1 if el.tag == 'forward' else -1)
                elif el.tag == 'note' and el.find('grace') is None:
                    duration = Fraction(int(el.findtext('duration')), divisions)
                    chord = el.find('chord') is not None
                    onset = previous_start if chord else cursor
                    if not chord:
                        previous_start = cursor
                        cursor += duration
                    pitch = el.find('pitch')
                    if pitch is None:
                        continue
                    staff = el.findtext('staff', '1')
                    step, octave = pitch.findtext('step'), int(pitch.findtext('octave'))
                    alteration = int(pitch.findtext('alter', '0'))
                    text = el.findtext('accidental')
                    declared = ACCIDENTALS[text] if text is not None else None
                    if text is not None and declared != alteration:
                        raise ValueError('Printed accidental disagrees with encoded pitch')
                    continuation = el.find("tie[@type='stop']") is not None
                    groups[onset, staff, step, octave].append((alteration, declared, continuation))
            state = {}
            for (onset, staff, step, octave), notes in sorted(groups.items()):
                previous = state.get((staff, step, octave), keys.get(staff, {}).get(step, 0))
                values = {n[0] for n in notes}
                declarations = {n[1] for n in notes if n[1] is not None}
                for alteration, declared, continuation in notes:
                    checked += 1
                    displayed += declared is not None
                    tied += continuation
                    if declared is None and not continuation:
                        shared = len(values) == 1 and declarations == {alteration}
                        if not shared and (len(values) > 1 or previous != alteration):
                            raise ValueError(f'Missing necessary accidental: measure {measure.get("number")}, '
                                             f'staff {staff}, onset {onset}, {step}{octave}, '
                                             f'encoded {alteration}, apparent {previous}')
                if any(not n[2] for n in notes):
                    state[staff, step, octave] = next(iter(values)) if len(values) == 1 else None
    return {'status': 'PASS', 'pitch_segments_checked': checked, 'displayed_accidentals': displayed,
            'tied_continuations': tied,
            'scope': 'Visible accidental semantics versus encoded pitches, not pixel collision or recognition accuracy.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('musicxml', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.musicxml)))
    except (OSError, ValueError, KeyError, ET.ParseError) as exc:
        parser.exit(1, f'Engraving verification failed: {exc}\n')
