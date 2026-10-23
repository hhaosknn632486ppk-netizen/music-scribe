"""Verify this source artifact's manifest; optional strict export check (stdlib)."""
import argparse,hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--strict',action='store_true',help='Also reject any file not in the source manifest')
    args=parser.parse_args()
    manifest=json.loads((ROOT/'MANIFEST.json').read_text(encoding='utf-8'))
    expected={'MANIFEST.json'}
    for item in manifest['files']:
        path=(ROOT/item['path']).resolve()
        if not path.is_relative_to(ROOT.resolve()) or not path.is_file():raise ValueError('Missing/unsafe file: '+item['path'])
        if path.stat().st_size!=item['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('Source checksum mismatch: '+item['path'])
        expected.add(item['path'])
    actual={path.relative_to(ROOT).as_posix() for path in ROOT.rglob('*')
            if path.is_file() and path.relative_to(ROOT).parts[0] != '.git'}
    extra=sorted(actual-expected)
    if args.strict and extra:raise ValueError('Unmanifested files: '+', '.join(extra))
    print(json.dumps({'status':'PASS','manifest_files':len(manifest['files']),'extra_files':extra,
                      'scope':'Artifact integrity only; not a license/recognition-accuracy guarantee.'},ensure_ascii=False))
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError) as exc:raise SystemExit('Source verification failed: '+str(exc))
