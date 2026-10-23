"""Fresh-process / reused-session benchmark and bounded Python socket denial.

No downloads. This script is a test helper, not an accuracy evaluator.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audio',type=Path)
    parser.add_argument('-o','--out',required=True,type=Path)
    parser.add_argument('--worker',action='store_true')
    parser.add_argument('--runs',type=int,default=2)
    parser.add_argument('--block-python-network',action='store_true')
    parser.add_argument('--cache',type=Path)
    args=parser.parse_args()
    if args.runs<1: parser.error('runs must be positive')
    if not args.worker and args.out.exists() and any(args.out.iterdir()): parser.error('Output must be empty')
    args.out.mkdir(parents=True,exist_ok=True)
    if not args.worker:
        env=dict(os.environ,OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
        command=[sys.executable,str(Path(__file__).resolve()),str(args.audio.resolve()),'-o',str(args.out.resolve()),'--worker','--runs',str(args.runs)]
        if args.block_python_network: command+=['--block-python-network']
        if args.cache: command+=['--cache',str(args.cache.resolve())]
        started=time.perf_counter()
        env['MUSIC_SEMANTICS_BENCH_START']=str(started)
        with (args.out/'worker.log').open('w',encoding='utf-8') as log:
            proc=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT)
        record={'exit_code':proc.returncode,'fresh_process_wall_seconds':time.perf_counter()-started,'includes_imports':True}
        (args.out/'process.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
        print(json.dumps(record),flush=True)
        return proc.returncode
    import socket
    attempts=[]
    if args.block_python_network:
        def denied(*values,**kwargs):
            attempts.append('socket_call_blocked')
            raise OSError('Network deliberately denied by benchmark')
        socket.create_connection=denied; socket.socket.connect=denied; socket.socket.connect_ex=denied; socket.getaddrinfo=denied
    imported=time.perf_counter()
    import music_semantics as ms
    engine=ms.Engine(); runs=[]; first_completed=None
    for i in range(args.runs):
        t=time.perf_counter()
        doc=ms.analyze(args.audio,args.out/f'run_{i}',engine=engine,cache_dir=args.cache)
        if not i: first_completed=time.perf_counter()
        rows={'run':i,'mode':'first_in_process' if not i else 'reused_model_sessions',
            'wall_seconds':time.perf_counter()-t,'status':doc['status'],'timings_seconds':doc.get('timings_seconds'),
            'resources':doc.get('resources'),'cache':doc.get('cache'),'summary_zh':doc.get('summary_zh')}
        runs.append(rows)
        print(json.dumps(rows,ensure_ascii=False),flush=True)
    record={'audio':str(args.audio.resolve()),'imports_and_engine_setup_seconds':time.perf_counter()-imported-sum(r['wall_seconds'] for r in runs),
        'fresh_process_to_first_output_seconds':first_completed-float(os.environ.get('MUSIC_SEMANTICS_BENCH_START',str(imported))),
        'runs':runs,'python_socket_denial_enabled':args.block_python_network,'blocked_attempts':attempts,
        'network_proof_limit':'Python socket denial only; no OS firewall/airgap or native-process network trace.',
        'environment':{'python':sys.version,'processor':os.environ.get('PROCESSOR_IDENTIFIER'),'logical_cpus':os.cpu_count(),
            'openblas_threads':os.environ.get('OPENBLAS_NUM_THREADS'),'omp_threads':os.environ.get('OMP_NUM_THREADS')}}
    import importlib.metadata
    record['packages']={name:importlib.metadata.version(name) for name in ['numpy','scipy','onnxruntime','soxr','soundfile','imageio-ffmpeg']}
    ms.write_json(args.out/'benchmark.json',record)
    return 0 if all(row['status']!='unavailable' for row in runs) else 4

if __name__=='__main__': raise SystemExit(main())
