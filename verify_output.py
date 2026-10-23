"""Check generated evidence and full MusicXML against retained detector events.

This validates consistency and provenance pairing, not music recognition accuracy.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

import music_scribe as ms
from verify_musicxml import read_intervals


def verify(folder):
    data = json.loads((folder / 'report.json').read_text(encoding='utf-8'))
    if data['schema_version'] != ms.SCHEMA_VERSION:
        raise ValueError('Unsupported report schema')
    code_matches = ms.file_fingerprint(Path(ms.__file__))['sha256'] == data['provenance']['code']['sha256']
    if not code_matches:
        raise ValueError('Report code SHA256 differs from this copy')
    info = data['evidence_files']['events']
    event_file = (folder / info['name']).resolve()
    if event_file.parent != folder.resolve() or ms.file_fingerprint(event_file)['sha256'] != info['sha256']:
        raise ValueError('Event evidence path or SHA256 mismatch')
    events = json.loads(event_file.read_text(encoding='utf-8'))['events']
    by_id = {e['id']: e for e in events}
    if len(by_id) != len(events) or len(events) != data['notes']:
        raise ValueError('Duplicate event IDs or wrong note count')
    for event in events:
        if not (0 <= event['t0'] < event['t1'] and event['pitch_class'] == event['midi'] % 12):
            raise ValueError('Invalid event interval or pitch class')
    previous_end = 0.0
    for chord in data['chords']:
        if abs(chord['t0'] - previous_end) > 1e-7 or chord['t1'] <= chord['t0']:
            raise ValueError('Chord timeline has a gap or overlapping spans')
        previous_end = chord['t1']
        if chord['support_count'] != len(chord['supported_pitch_classes']):
            raise ValueError('Wrong chord support count')
        if set(chord['missing_pitch_classes']) != set(chord['chord_pitch_classes']) - set(chord['supported_pitch_classes']):
            raise ValueError('Wrong missing chord tones')
        for event_id in chord['source_event_ids']:
            event = by_id[event_id]
            if not (event['t0'] < chord['t1'] and event['t1'] > chord['t0']):
                raise ValueError('Chord cites an event outside its time range')
        for event_id in chord['support_event_ids']:
            if event_id not in chord['source_event_ids'] or by_id[event_id]['pitch_class'] not in chord['supported_pitch_classes']:
                raise ValueError('Invalid supporting event reference')
    if abs(previous_end - data['duration']) > 1e-7:
        raise ValueError('Chord timeline does not cover the original duration')
    result = {'schema': ms.SCHEMA_VERSION, 'events': len(events), 'chord_segments': len(data['chords']),
              'evidence_checks': 'PASS', 'full_score': 'not_applicable',
              'scope': 'Output consistency only; no independently annotated recognition accuracy.'}
    if data['score_mode'] == 'full' and data['artifacts']['musicxml']['status'] == 'written':
        qn = ms.quantize([(e['t0'], e['t1'], e['midi'], e['activation']) for e in events], data['bpm'],
                         origin=data['bar_origin_seconds'])
        expected = Counter((n['p'], round(n['o'], 6), round(n['d'], 6)) for n in qn)
        actual, stats = read_intervals(folder / data['artifacts']['musicxml']['name'])
        result['full_score'] = dict(stats, expected_intervals=sum(expected.values()),
            missing_or_changed=sum((expected - actual).values()), extra_or_changed=sum((actual - expected).values()))
        if actual != expected:
            raise ValueError(f'Full MusicXML differs from quantized events: {result["full_score"]}')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_folder', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.output_folder), ensure_ascii=False))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f'Verification failed: {exc}\n')
