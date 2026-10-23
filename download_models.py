"""Explicit local-model acquisition. Standard library only; never imported by inference.

Metadata and SHA256 values come from the bundled, fixed models/manifest.json.
No license conflict is resolved by this script or by answering yes.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent
ORDER = ('gate', 'effnet', 'moodtheme', 'voice', 'musicnn', 'deam')
PURPOSE = {'gate':'music/non-music gate', 'effnet':'400-style backbone',
           'moodtheme':'56 mood/theme labels', 'voice':'voice/instrumental tendency',
           'musicnn':'50-tag backbone', 'deam':'continuous valence/arousal'}
CONFLICT = ('UNRESOLVED: MTG official overview declares CC BY-NC-SA 4.0 (the five official model JSON files have no license field), '
            'but the supplied LICENSE also contains NoDerivatives wording/body. '
            'See LICENSE_STATUS.md. Confirmation does not resolve this conflict '
            'or grant commercial permission.')


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def target_path(folder, record):
    name = record['name']
    if not isinstance(name, str) or not name or name in ('.','..') or '/' in name or '\\' in name or ':' in name:
        raise ValueError('Unsafe manifest filename')
    path = Path(folder)/name
    if path.is_symlink() or path.resolve().parent != Path(folder).resolve():
        raise ValueError('Refusing a symlink or path outside model directory: '+name)
    return path


def matches(path, record):
    return path.is_file() and path.stat().st_size == record['bytes'] and sha256(path) == record['sha256']


def selected(manifest, only):
    keys = ('gate',) if only == 'gate' else ORDER
    for key in keys:
        item = manifest['models'][key]
        for part in ('weights','metadata'):
            record = item[part]
            target_path(ROOT, record)
            if not isinstance(record['bytes'],int) or record['bytes'] <= 0:
                raise ValueError('Invalid manifest size')
            if len(record['sha256']) != 64 or any(c not in '0123456789abcdef' for c in record['sha256']):
                raise ValueError('Invalid manifest SHA256')
        if not item['official_url'].startswith('https://'):
            raise ValueError('Only HTTPS model URLs are allowed')
    return keys


def show_licenses(manifest, keys, output=print):
    for key in keys:
        item=manifest['models'][key]
        output(f"{key}: {item['weights']['name']} | {item['weights']['bytes']} bytes | {item['license']} | {PURPOSE[key]}")
        output('  Source: '+item['official_url'])
    if any(key != 'gate' for key in keys):
        output(CONFLICT)
    else:
        output('Gate only: Apache-2.0. This downloads one model; full semantics still requires all six.')
    output('Only an explicit download action accesses the network. Inference never invokes this script.')


def check_store(manifest, keys, folder):
    return {key:{part:matches(target_path(folder,manifest['models'][key][part]),manifest['models'][key][part])
                 for part in ('weights','metadata')} for key in keys}


def write_verified_bytes(folder, record, data, repair=False):
    dest=target_path(folder,record)
    if matches(dest,record): return
    if dest.exists() and not repair:
        raise ValueError('Existing metadata differs; inspect it or explicitly use --repair: '+dest.name)
    if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
        raise ValueError('Bundled metadata checksum mismatch: '+dest.name)
    temp=None
    try:
        with tempfile.NamedTemporaryFile(dir=folder,prefix='.metadata-',suffix='.part',delete=False) as stream:
            temp=Path(stream.name);stream.write(data);stream.flush();os.fsync(stream.fileno())
        temp.replace(dest)
    finally:
        if temp is not None: temp.unlink(missing_ok=True)


def download_one(item, folder, timeout=30., repair=False, opener=None):
    record=item['weights'];dest=target_path(folder,record)
    if matches(dest,record): return 'already_verified'
    if dest.exists() and not repair:
        raise ValueError('Existing weight is corrupt/different; left untouched. Use --repair explicitly: '+dest.name)
    if not item['official_url'].startswith('https://'):
        raise ValueError('Only HTTPS model URLs are allowed')
    request=urllib.request.Request(item['official_url'],headers={'User-Agent':'music-scribe-source/1.0'})
    opener=opener or urllib.request.urlopen
    temp=None
    try:
        with opener(request,timeout=timeout) as response:
            if getattr(response,'status',200) != 200:
                raise ValueError('Unexpected HTTP status')
            if not response.geturl().startswith('https://'):
                raise ValueError('Refusing HTTPS downgrade')
            length=response.headers.get('Content-Length')
            if length is not None and int(length) != record['bytes']:
                raise ValueError('HTTP size differs from fixed manifest: '+dest.name)
            digest=hashlib.sha256();total=0
            with tempfile.NamedTemporaryFile(dir=folder,prefix='.download-',suffix='.part',delete=False) as stream:
                temp=Path(stream.name)
                while True:
                    block=response.read(min(1024*1024,record['bytes']-total+1))
                    if not block: break
                    total+=len(block)
                    if total>record['bytes']: raise ValueError('Download exceeds fixed size: '+dest.name)
                    stream.write(block);digest.update(block)
                stream.flush();os.fsync(stream.fileno())
            if total != record['bytes'] or digest.hexdigest() != record['sha256']:
                raise ValueError('SHA256/size mismatch; rejected download: '+dest.name)
        temp.replace(dest)
        return 'downloaded_verified'
    finally:
        if temp is not None: temp.unlink(missing_ok=True)


def acquire(manifest, keys, folder, bundled, repair=False, timeout=30., opener=None, output=print):
    folder=Path(folder);bundled=Path(bundled)
    # Validate all bundled metadata before any network request or destination mutation.
    payloads={}
    for key in keys:
        record=manifest['models'][key]['metadata'];path=target_path(bundled,record)
        if not matches(path,record): raise ValueError('Bundled metadata checksum mismatch: '+path.name)
        payloads[key]=path.read_bytes()
    folder.mkdir(parents=True,exist_ok=True)
    # Existing invalid files are never implicitly deleted or repaired.
    for key in keys:
        for part in ('weights','metadata'):
            record=manifest['models'][key][part];path=target_path(folder,record)
            if path.exists() and not matches(path,record) and not repair:
                raise ValueError('Existing '+part+' differs; left untouched. Inspect or explicitly use --repair: '+path.name)
    result={}
    for key in keys:
        item=manifest['models'][key]
        state=download_one(item,folder,timeout,repair,opener)
        write_verified_bytes(folder,item['metadata'],payloads[key],repair)
        result[key]=state
        output(key+': '+state)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only',choices=('gate','semantics'),default='semantics',help='semantics = all six existing models')
    parser.add_argument('--models-dir',type=Path,default=Path(os.environ.get('MUSIC_SCRIBE_MODELS') or ROOT/'models'))
    parser.add_argument('--yes',action='store_true',help='Explicit non-interactive confirmation after reading the displayed licenses and unresolved conflict')
    parser.add_argument('--repair',action='store_true',help='Replace a corrupt/different selected file only after verifying its replacement')
    parser.add_argument('--check',action='store_true',help='Verify local selected weights/metadata only; no download or confirmation')
    parser.add_argument('--list',action='store_true',help='Show selected licenses and sources only; no download')
    parser.add_argument('--timeout',type=float,default=30.)
    args=parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout<=0: parser.error('timeout must be positive and finite')
    try:
        manifest=json.loads((ROOT/'models/manifest.json').read_text(encoding='utf-8'))
        keys=selected(manifest,args.only)
        show_licenses(manifest,keys)
        if args.list: return 0
        if args.check:
            result=check_store(manifest,keys,args.models_dir)
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 0 if all(all(value.values()) for value in result.values()) else 1
        if not args.yes:
            try: answer=input('Read LICENSE_STATUS.md and the above licenses. Confirm local acquisition? Type yes: ')
            except EOFError: answer=''
            if answer.strip().lower()!='yes':
                print('Not confirmed; no weights downloaded.');return 2
        acquire(manifest,keys,args.models_dir,ROOT/'models',args.repair,args.timeout)
        return 0
    except (OSError,ValueError,KeyError) as exc:
        print('Model acquisition failed: '+str(exc),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
