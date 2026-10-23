"""Check generated MusicXML beam continuity and report notation metrics.

This supplements verify_output.py; it does not establish recognition accuracy
or pixel-perfect engraving. Staff-silence rest policy is an optional check.
"""
import argparse
from collections import defaultdict
from fractions import Fraction
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def inspect_layout(path, check_beams=True, check_staff_rests=False):
    root = ET.parse(path)
    metrics = dict(pitched_segments=0, chord_members=0, visible_rests=0, hidden_rests=0,
                   beam_elements=0, primary_beam_groups=0, beam_hooks=0,
                   visible_rest_note_overlaps=0)
    voice_counts = []
    for part in root.findall('part'):
        divisions = None
        for measure in part.findall('measure'):
            lanes, pitches, rests = defaultdict(list), defaultdict(list), []
            pitched_voices = defaultdict(set)
            cursor, previous_start = Fraction(0), Fraction(0)
            for el in measure:
                if el.tag == 'attributes' and el.findtext('divisions') is not None:
                    divisions = int(el.findtext('divisions'))
                elif el.tag in ('backup', 'forward'):
                    cursor += Fraction(int(el.findtext('duration')), divisions) * (1 if el.tag == 'forward' else -1)
                elif el.tag == 'note' and el.find('grace') is None:
                    duration = Fraction(int(el.findtext('duration')), divisions)
                    chord = el.find('chord') is not None
                    onset = previous_start if chord else cursor
                    if not chord:
                        previous_start = cursor
                        cursor += duration
                    staff, voice = el.findtext('staff', '1'), el.findtext('voice', '1')
                    pitched = el.find('pitch') is not None
                    if pitched:
                        metrics['pitched_segments'] += 1
                        metrics['chord_members'] += int(chord)
                        pitches[staff].append((onset, onset + duration))
                        pitched_voices[staff].add(voice)
                        if el.get('print-object') == 'no':
                            raise ValueError('A pitched note was hidden')
                    else:
                        hidden = el.get('print-object') == 'no'
                        metrics['hidden_rests' if hidden else 'visible_rests'] += 1
                        if not hidden:
                            rests.append((staff, onset, onset + duration))
                    beams = {}
                    for b in el.findall('beam'):
                        level = int(b.get('number', '1'))
                        if level in beams or not 1 <= level <= 8:
                            raise ValueError('Duplicate or unsupported beam level')
                        beams[level] = b.text
                        metrics['beam_elements'] += 1
                        metrics['primary_beam_groups'] += int(level == 1 and b.text == 'begin')
                        metrics['beam_hooks'] += int(b.text in ('forward hook', 'backward hook'))
                    if not chord:
                        lanes[staff, voice].append((onset, duration, pitched, beams))
            voice_counts.extend(len(v) for v in pitched_voices.values())
            for staff, start, end in rests:
                if any(start < b and end > a for a, b in pitches[staff]):
                    metrics['visible_rest_note_overlaps'] += 1
            if check_beams:
                for lane, events in lanes.items():
                    active = {}
                    for index, (onset, duration, pitched, beams) in enumerate(events):
                        if set(active) - set(beams):
                            raise ValueError(f'Beam crossed a gap/rest/unbeamed note: {lane}')
                        if beams and not pitched:
                            raise ValueError('A rest unexpectedly carries beams')
                        for level, role in beams.items():
                            if level > 1 and level - 1 not in beams:
                                raise ValueError('Beam level lacks its parent')
                            if role == 'begin':
                                if level in active:
                                    raise ValueError('Beam restarted before it ended')
                                active[level] = onset + duration
                            elif role in ('continue', 'end'):
                                if active.get(level) != onset:
                                    raise ValueError('Orphan or noncontiguous beam continuation/end')
                                if role == 'end':
                                    del active[level]
                                else:
                                    active[level] = onset + duration
                            elif role in ('forward hook', 'backward hook'):
                                if level == 1 or level in active:
                                    raise ValueError('Unsupported primary or active beam hook')
                                neighbor = index + (1 if role == 'forward hook' else -1)
                                if not 0 <= neighbor < len(events):
                                    raise ValueError('Beam hook points outside its voice')
                                other_start, other_duration, other_pitched, other_beams = events[neighbor]
                                touching = onset + duration == other_start if role == 'forward hook' else other_start + other_duration == onset
                                if not other_pitched or not touching or 1 not in other_beams:
                                    raise ValueError('Beam hook points into a gap/rest')
                            else:
                                raise ValueError('Unknown beam role')
                    if active:
                        raise ValueError('Unclosed beam groups')
    if check_staff_rests and metrics['visible_rest_note_overlaps']:
        raise ValueError('Visible rest overlaps a sounding note on the same staff')
    metrics['maximum_pitched_voices_per_staff_measure'] = max(voice_counts, default=0)
    metrics['mean_pitched_voices_per_staff_measure'] = round(sum(voice_counts) / len(voice_counts), 4) if voice_counts else 0.
    return {'status': 'PASS' if check_beams else 'metrics_only', 'metrics': metrics,
            'staff_silence_rest_policy_checked': check_staff_rests,
            'scope': 'Beam structure and generated rest policy only; not note accuracy, voice identity or visual-collision certification.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('musicxml', type=Path)
    parser.add_argument('--check-staff-rests', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(inspect_layout(args.musicxml, check_staff_rests=args.check_staff_rests)))
    except (OSError, ValueError, TypeError, ET.ParseError) as exc:
        parser.exit(1, f'Layout verification failed: {exc}\n')
