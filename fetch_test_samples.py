"""Explicit test-data download. Never imported by the analysis runtime."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-o','--out',required=True,type=Path)
    args=parser.parse_args(); args.out.mkdir(parents=True,exist_ok=True)
    sources=json.loads((Path(__file__).resolve().parent/'samples/SAMPLES.json').read_text(encoding='utf-8'))
    print('Explicit example-data download; read samples/README.md for attribution and scope.')
    for source in sources:
        if not source['audio'].get('url'):
            print('SKIP local/derived input:',source['key'])
            continue
        for kind in ['audio']:
            value=source[kind]; target=args.out/Path(value['path']).name
            if not target.exists():
                with urllib.request.urlopen(value['url'],timeout=60) as response: data=response.read()
                if hashlib.sha256(data).hexdigest()!=value['sha256']: raise ValueError('Source hash differs: '+source['key'])
                target.write_bytes(data)
            if hashlib.sha256(target.read_bytes()).hexdigest()!=value['sha256']: raise ValueError('Existing file hash differs: '+str(target))
        print(source['key'],str(args.out/Path(source['audio']['path']).name))
    return 0

if __name__=='__main__': raise SystemExit(main())
