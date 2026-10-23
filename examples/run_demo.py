"""Run the documented local music/speech demo. SPDX-License-Identifier: AGPL-3.0-or-later.

Audio must already exist locally. Use fetch_test_samples.py explicitly beforehand.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio-dir', required=True, type=Path)
    parser.add_argument('--models-dir', required=True, type=Path)
    parser.add_argument('--output-root', required=True, type=Path)
    parser.add_argument('--with-score',action='store_true',help='Full environment only: also transcribe the first 12 seconds of the public music example')
    args = parser.parse_args()
    if args.with_score and any(importlib.util.find_spec(name) is None for name in ('basic_pitch','music21','verovio')):
        parser.error('--with-score requires the full compatibility environment; see INSTALL.md')
    rows = json.loads((ROOT / 'samples/SAMPLES.json').read_text(encoding='utf-8'))
    inputs = {row['key']: args.audio_dir.resolve() / Path(row['audio']['path']).name for row in rows}
    for key in ('brahms', 'libri1'):
        if not inputs[key].is_file():
            parser.error('Missing ' + str(inputs[key]) + '; first run fetch_test_samples.py explicitly')
    folder = args.output_root.resolve() / ('demo-' + uuid.uuid4().hex[:10])
    folder.mkdir(parents=True)
    env = dict(os.environ, MUSIC_SCRIBE_MODELS=str(args.models_dir.resolve()),
               PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
    receipt = {'scope': 'Two public examples; execution demonstration, not a new accuracy evaluation.',
               'models_dir': str(args.models_dir.resolve()), 'samples': {}}
    for key in ('brahms', 'libri1'):
        command = [sys.executable, '-B', str(ROOT / 'examples/llm_tool.py'), 'analyze',
                   '--audio', str(inputs[key]), '--output-root', str(folder / key),
                   '--task', 'semantics', '--models-dir', str(args.models_dir.resolve())]
        process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                 encoding='utf-8', env=env, timeout=1800)
        result = json.loads(process.stdout)
        (folder / (key + '.tool.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        if process.returncode:
            print(json.dumps({'status': 'error', 'sample': key, 'tool_result': result}, ensure_ascii=False))
            return process.returncode
        output = Path(result['output_dir'])
        checked = subprocess.run([sys.executable, '-B', str(ROOT / 'verify_semantics.py'), str(output),
                                  '--models-dir', str(args.models_dir.resolve())],
                                 cwd=ROOT, capture_output=True, text=True, encoding='utf-8', env=env, timeout=120)
        if checked.returncode:
            print(checked.stderr, file=sys.stderr)
            return 2
        end = min(8., result['summary']['duration'])
        lookup = subprocess.run([sys.executable, '-B', str(ROOT / 'examples/llm_tool.py'), 'query',
                                 '--report', result['query_report'], '--start', '0', '--end', str(end)],
                                cwd=ROOT, capture_output=True, text=True, encoding='utf-8', env=env, timeout=60)
        if lookup.returncode:
            print(lookup.stderr or lookup.stdout, file=sys.stderr)
            return 2
        local = json.loads(lookup.stdout)
        (folder / (key + '.query.json')).write_text(json.dumps(local, ensure_ascii=False, indent=2), encoding='utf-8')
        receipt['samples'][key] = {'analysis_status': result['summary']['status'],
                                   'music_presence': result['summary'].get('music_presence', {}).get('status'),
                                   'output_dir': str(output), 'tool_result': str(folder / (key + '.tool.json')),
                                   'query_result': str(folder / (key + '.query.json')),
                                   'evidence_consistency': json.loads(checked.stdout)['status']}
    if args.with_score:
        import soundfile as sf
        sr=sf.info(inputs['brahms']).samplerate
        audio,sr=sf.read(inputs['brahms'],frames=sr*12)
        clip=folder/'brahms-first12s.wav'
        sf.write(clip,audio,sr,subtype='PCM_16')
        command=[sys.executable,'-B',str(ROOT/'examples/llm_tool.py'),'analyze','--audio',str(clip),
                 '--output-root',str(folder/'score'),'--task','all','--models-dir',str(args.models_dir.resolve())]
        process=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',env=env,timeout=1800)
        response=json.loads(process.stdout)
        (folder/'score.tool.json').write_text(json.dumps(response,ensure_ascii=False,indent=2),encoding='utf-8')
        if process.returncode:
            print(json.dumps({'status':'error','stage':'score','tool_result':response},ensure_ascii=False))
            return process.returncode
        verification={}
        for name,arguments in [('score',['verify_output.py',response['output_dir']]),
                               ('semantics',['verify_semantics.py',response['output_dir'],'--models-dir',str(args.models_dir.resolve())])]:
            checked=subprocess.run([sys.executable,'-B',str(ROOT/arguments[0]),*arguments[1:]],cwd=ROOT,
                                   capture_output=True,text=True,encoding='utf-8',env=env,timeout=120)
            if checked.returncode:
                print(json.dumps({'status':'partial','stage':name+'_verification','error':checked.stderr,
                                  'output_dir':response['output_dir']},ensure_ascii=False))
                return 3
            verification[name]=json.loads(checked.stdout)
        receipt['score_example']={'source':'First 12 seconds of the downloaded public Brahms example, PCM16 WAV.',
                                  'output_dir':response['output_dir'],'artifacts':response['artifacts'],
                                  'verification':verification}
    instructions = (ROOT / 'examples/assistant_prompt.txt').read_text(encoding='utf-8')
    (folder / 'ASSISTANT_PROMPT.txt').write_text(instructions, encoding='utf-8')
    (folder / 'DEMO_RESULT.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': 'completed', 'demo_dir': str(folder), **receipt}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
    raise SystemExit(main())
