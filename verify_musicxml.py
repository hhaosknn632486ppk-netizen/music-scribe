"""Read MusicXML note intervals with explicit staff/voice tie-chain validation.

QuarterLength units only. Uses rational division; no MIDI tempo assumptions.
This avoids music21.stripTies() combining notes across notation voices.
"""
from collections import Counter
from fractions import Fraction
from pathlib import Path
import xml.etree.ElementTree as ET


def read_intervals(path):
    xml = ET.parse(path)
    intervals, active = [], {}
    continuation_count = 0
    for part_index, part in enumerate(xml.findall('part')):
        measure_start = Fraction(0)
        divisions = None
        for measure in part.findall('measure'):
            cursor = Fraction(0)
            extent = Fraction(0)
            previous_start = Fraction(0)
            for element in measure:
                if element.tag == 'attributes':
                    text = element.findtext('divisions')
                    if text is not None:
                        divisions = int(text)
                    continue
                if element.tag in ('backup', 'forward'):
                    duration = Fraction(int(element.findtext('duration')), divisions)
                    cursor += duration if element.tag == 'forward' else -duration
                    extent = max(extent, cursor)
                    if cursor < 0:
                        raise ValueError('MusicXML backup moved before measure start')
                    continue
                if element.tag != 'note' or element.find('grace') is not None:
                    continue
                duration = Fraction(int(element.findtext('duration')), divisions)
                is_chord = element.find('chord') is not None
                onset = previous_start if is_chord else cursor
                if not is_chord:
                    previous_start = cursor
                    cursor += duration
                extent = max(extent, onset + duration)
                pitch = element.find('pitch')
                if pitch is None:
                    continue
                midi = ((int(pitch.findtext('octave')) + 1) * 12
                        + {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}[pitch.findtext('step')]
                        + int(pitch.findtext('alter', '0')))
                key = (part_index, element.findtext('staff', '1'), element.findtext('voice', '1'), midi)
                absolute = measure_start + onset
                ties = {tie.get('type') for tie in element.findall('tie')}
                if 'stop' in ties:
                    continuation_count += 1
                    if key not in active or active[key][1] != absolute:
                        raise ValueError(f'Unmatched or noncontiguous tie stop: {key}, onset={absolute}')
                    start, _ = active[key]
                else:
                    if key in active:
                        raise ValueError(f'New attack before previous tie chain closed: {key}')
                    start = absolute
                if 'start' in ties:
                    active[key] = (start, absolute + duration)
                else:
                    active.pop(key, None)
                    intervals.append((midi, round(float(start), 6), round(float(absolute + duration - start), 6)))
            measure_start += extent
    if active:
        raise ValueError(f'Unclosed tie chains: {active}')
    return Counter(intervals), {'logical_note_intervals': len(intervals),
                                'tied_continuation_segments': continuation_count}


if __name__ == '__main__':
    import json
    import sys
    counter, metrics = read_intervals(Path(sys.argv[1]))
    print(json.dumps(metrics))
