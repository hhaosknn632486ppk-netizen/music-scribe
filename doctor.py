"""Inspect the tested platform and dependency group without downloading models."""
import argparse
import importlib.metadata
import json
import platform
import sys

CORE={'setuptools':'80.9.0','numpy':'2.2.6','scipy':'1.15.3','librosa':'0.11.0','soundfile':'0.14.0',
      'soxr':'1.1.0','onnxruntime':'1.23.2','imageio-ffmpeg':'0.6.0','basic-pitch':'0.4.0',
      'pretty-midi':'0.2.11','mido':'1.3.3','music21':'9.9.2','verovio':'6.3.0'}
SEMANTICS={key:CORE[key] for key in ('numpy','scipy','soundfile','soxr','onnxruntime','imageio-ffmpeg')}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('core','semantics','all'),default='all')
    args=parser.parse_args()
    expected=SEMANTICS if args.mode=='semantics' else CORE
    rows=[]
    for name,version in expected.items():
        try:actual=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:actual=None
        rows.append({'package':name,'expected':version,'actual':actual,'matches':actual==version})
    versions=((3,10),(3,12)) if args.mode=='semantics' else ((3,10),)
    supported=sys.platform=='win32' and sys.version_info[:2] in versions and platform.architecture()[0]=='64bit'
    print(json.dumps({'python':platform.python_version(),'platform':sys.platform,'tested_target_matches':supported,
                      'tested_python_profiles':['3.10','3.12'] if args.mode=='semantics' else ['3.10'],
                      'profile_note':'Python 3.10 is a legacy compatibility profile and has reached upstream end-of-life; see INSTALL.md.',
                      'dependencies':rows,'models':'Not loaded or downloaded; use download_models.py --check separately.'},ensure_ascii=False,indent=2))
    return 0 if supported and all(row['matches'] for row in rows) else 1
if __name__=='__main__':raise SystemExit(main())
