"""Explicit local sample runner; reports missing/error cases, never downloads.

--package can point at the preserved 1.2 directory for the paired baseline.
Use benchmark_semantics.py for fresh-process performance, not this reused engine.
"""
import argparse,json,socket,sys
from pathlib import Path
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=Path(__file__).resolve().parent/'samples/SAMPLES.json')
    parser.add_argument('--package',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--audio-dir',type=Path)
    parser.add_argument('-o','--out',required=True,type=Path)
    parser.add_argument('--block-python-network',action='store_true')
    args=parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()): parser.error('Output must be empty')
    args.out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(args.package.resolve())); import music_semantics as ms
    attempts=[]
    if args.block_python_network:
        def denied(*a,**kw): attempts.append('blocked'); raise OSError('Python network deliberately blocked')
        socket.create_connection=denied; socket.socket.connect=denied; socket.socket.connect_ex=denied; socket.getaddrinfo=denied
    engine=ms.Engine(); observations=[]
    for source in json.loads(args.manifest.read_text(encoding='utf-8')):
        value=source['audio']; path=Path(value['path'])
        if args.audio_dir and (args.audio_dir/path.name).is_file(): path=args.audio_dir/path.name
        row={'key':source['key'],'split':source['split'],'role':source['role']}
        if not path.is_file(): row.update(status='missing',reason=str(path))
        elif ms.sha(path)!=value['sha256']: row.update(status='error',reason='input SHA256 differs')
        else:
            try:
                doc=ms.analyze(path,args.out/source['key'],engine=engine)
                row.update(status=doc['status'],source_sha256=doc['source']['sha256'],
                    styles_emitted='styles' in doc.get('global',{}),music_presence=doc.get('music_presence'),summary_zh=doc.get('summary_zh'))
            except Exception as exc: row.update(status='error',reason=str(exc))
        observations.append(row); print(source['key'],row['status'],flush=True)
    report={'requested':len(observations),'missing':sum(r['status']=='missing' for r in observations),
        'errors':sum(r['status'] in ('error','unavailable') for r in observations),'observations':observations,
        'python_network_attempts':attempts,'scope':'Execution and style-output observations; no musical accuracy estimate. Missing/errors remain explicit.'}
    (args.out/'EVALUATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 2 if report['errors'] or report['missing'] else 0
if __name__=='__main__': raise SystemExit(main())
