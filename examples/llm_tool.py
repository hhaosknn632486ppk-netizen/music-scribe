"""Local command tool for an AI assistant. SPDX-License-Identifier: AGPL-3.0-or-later.

No API key, network client, model download or shell=True. Stdout is one JSON object.
"""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def child_environment():
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
    env.setdefault('OPENBLAS_NUM_THREADS', '2')
    env.setdefault('OMP_NUM_THREADS', '2')
    return env


def execute(arguments, timeout):
    return subprocess.run([sys.executable, '-B', str(ROOT / 'music_scribe.py'), *arguments],
                          cwd=ROOT, shell=False, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=timeout,
                          env=child_environment())


def envelope(status, **fields):
    return {'schema_version': 'music-scribe-tool/1', 'status': status,
            'analysis_runs_locally': True, 'downloads_models': False, **fields}


def analyze(audio, output_root, task='semantics', models_dir=None, timeout=1800):
    audio = Path(audio).expanduser().resolve()
    if not audio.is_file():
        return envelope('error', error='Audio file does not exist', audio=str(audio)), 2
    if task not in ('semantics', 'score', 'all'):
        return envelope('error', error='task must be semantics, score or all'), 2
    parent = Path(output_root).expanduser().resolve()
    # A fresh child folder avoids overwriting prior reports or confusing outputs.
    folder = parent / (datetime.now(timezone.utc).strftime('run-%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8])
    parent.mkdir(parents=True, exist_ok=True)
    arguments = [str(audio), '-o', str(folder)]
    if task == 'semantics':
        arguments.append('--semantics-only')
    else:
        arguments.extend(['--mode', 'full'])
        if task == 'all':
            arguments.append('--semantics')
    if models_dir is not None:
        arguments.extend(['--models-dir', str(Path(models_dir).expanduser().resolve())])
    try:
        result = execute(arguments, timeout)
    except subprocess.TimeoutExpired:
        return envelope('error', error='Analysis timed out', output_dir=str(folder), task=task), 2
    if folder.is_dir():
        (folder / 'analysis.stdout.log').write_text(result.stdout, encoding='utf-8')
        (folder / 'analysis.stderr.log').write_text(result.stderr, encoding='utf-8')
    summary_path = folder / 'summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.is_file() else None
    artifacts = {name: str(folder / name) for name in
                 ('summary.json', 'report.json', 'report.html', 'semantics.json', 'semantics.html',
                  'events.json', 'score.musicxml', 'transcription.mid') if (folder / name).is_file()}
    artifacts['svg_pages'] = [str(p) for p in sorted(folder.glob('score_p*.svg'))]
    semantic_doc = summary.get('semantics', summary) if isinstance(summary, dict) else {}
    unavailable = semantic_doc.get('status') == 'unavailable'
    status = ('completed' if result.returncode == 0 else
              'unavailable' if result.returncode == 4 else
              'partial' if result.returncode == 3 else 'error')
    if unavailable and result.returncode == 0:
        # A successful transcription can coexist with an unavailable optional branch.
        status = 'partial'
    report = artifacts.get('report.json') or artifacts.get('semantics.json')
    response = envelope(status, task=task, process_exit_code=result.returncode,
                        output_dir=str(folder), summary=summary, artifacts=artifacts,
                        query_report=report)
    if result.returncode not in (0, 3, 4):
        response['error'] = result.stderr.strip()[-3000:] or 'Analysis failed; inspect local logs'
    response['interpretation'] = (
        'Read status and warnings first. not_music, uncertain_input, insufficient_evidence and '
        'unavailable do not support a music-style or emotion claim. coarse does not permit fine-style '
        'inference. Scores are uncalibrated; title, artist and composer intent are not identified.')
    return response, result.returncode


def query(report, start, end, notes_limit=0, timeout=60):
    report = Path(report).expanduser().resolve()
    if not report.is_file():
        return envelope('error', error='Report file does not exist'), 2
    if not all(math.isfinite(x) for x in (start, end)) or not 0 <= start < end:
        return envelope('error', error='Require finite 0 <= start < end, in original audio seconds'), 2
    if not 0 <= notes_limit <= 1000:
        return envelope('error', error='notes_limit must be in 0..1000'), 2
    result = execute(['query', str(report), '--start', str(start), '--end', str(end),
                      '--notes-limit', str(notes_limit)], timeout)
    if result.returncode:
        return envelope('error', process_exit_code=result.returncode,
                        error=result.stderr.strip()[-3000:]), result.returncode
    return envelope('completed', result=json.loads(result.stdout)), 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    analysis = sub.add_parser('analyze', help='Run local analysis into a new child output folder')
    analysis.add_argument('--audio', required=True, type=Path)
    analysis.add_argument('--output-root', required=True, type=Path)
    analysis.add_argument('--task', choices=('semantics', 'score', 'all'), default='semantics')
    analysis.add_argument('--models-dir', type=Path)
    analysis.add_argument('--timeout', type=float, default=1800)
    lookup = sub.add_parser('query', help='Read existing evidence; no new inference')
    lookup.add_argument('--report', required=True, type=Path)
    lookup.add_argument('--start', required=True, type=float)
    lookup.add_argument('--end', required=True, type=float)
    lookup.add_argument('--notes-limit', type=int, default=0)
    args = parser.parse_args(argv)
    try:
        if args.command == 'analyze':
            if not math.isfinite(args.timeout) or args.timeout <= 0:
                raise ValueError('timeout must be positive and finite')
            response, code = analyze(args.audio, args.output_root, args.task, args.models_dir, args.timeout)
        else:
            response, code = query(args.report, args.start, args.end, args.notes_limit)
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        response, code = envelope('error', error=str(exc)), 2
    # The CLI's progress messages remain in local logs, outside this JSON result.
    print(json.dumps(response, ensure_ascii=False, allow_nan=False))
    return code


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
    raise SystemExit(main())
