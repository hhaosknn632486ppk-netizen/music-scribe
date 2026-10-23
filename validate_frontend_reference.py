"""Optional reference validation; Node/Essentia.js used only here, no downloads.

--reference-dir must point to extracted official essentia.js 0.1.3 package folder.
Pass local audio files to compare real PCM features and all five model outputs.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import numpy as np
import music_semantics as ms
import semantic_frontend as front

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-dir',required=True,type=Path)
    parser.add_argument('--audio',type=Path,action='append',default=[])
    parser.add_argument('-o','--out',required=True,type=Path)
    args=parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()): parser.error('Output must be empty')
    args.out.mkdir(parents=True,exist_ok=True); out=args.out.resolve()
    rows=[]; own={}; report={'thresholds':{'mel_max_abs':.0005,'output_max_abs':.002},'feature_comparisons':[],'model_comparisons':[]}
    def add(name,data,kind):
        data.astype('<f4').tofile(out/(name+'.f32'))
        rows.append({'name':name,'path':str(out/(name+'.f32')),'output':str(out/(name+'.reference.f32')),'kind':kind})
        own[name]=front.frame_features(data) if kind=='frames' else front.audio_features(data)
    with np.load(ms.ROOT/'tests/fixtures/frontend_fixture.npz',allow_pickle=False) as fixture:
        add('fixture',fixture['frames'],'frames')
    for n in [1,255,256,257,511,512,513,767,768,769,16001]:
        add('layout_'+str(n),.1+np.arange(n,dtype=np.float32)/max(n,1)*.1,'audio')
    for i,path in enumerate(args.audio):
        y,info=ms.decode(path)
        # Shared PCM, up to 12 seconds. Preserve codec/resampler fingerprint.
        y=y[16000*min(10,int(len(y)/16000/2)):][:16000*12]
        add('real_'+str(i),front.audio_frames(y),'frames')
        report.setdefault('sources',[]).append({'input':ms.fingerprint(path),'decode':info})
    ms.write_json(out/'manifest.json',rows)
    env=dict(os.environ,ESSENTIA_REFERENCE_DIR=str(args.reference_dir.resolve()))
    with (out/'reference.log').open('w',encoding='utf-8') as log:
        result=subprocess.run(['node',str(ms.ROOT/'tools/reference_frontend.cjs'),str(out/'manifest.json')],env=env,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode: raise RuntimeError('Reference failed; see reference.log')
    engine=ms.Engine()
    for row in rows:
        name=row['name']; reference=np.fromfile(row['output'],dtype='<f4').reshape(-1,96); candidate=own[name]
        delta=float(np.max(np.abs(reference-candidate))) if reference.shape==candidate.shape else None
        report['feature_comparisons'].append({'name':name,'reference_frames':len(reference),'candidate_frames':len(candidate),
            'max_abs':delta,'passed':delta is not None and delta<=.0005})
        if not name.startswith('real_') or len(reference)<187: continue
        for key,size,heads in [('effnet',128,['moodtheme','voice']),('musicnn',187,['deam'])]:
            starts=front.patches(reference,size)[:4]
            a=engine.run(key,np.stack([reference[s:s+size] for s in starts]))
            b=engine.run(key,np.stack([candidate[s:s+size] for s in starts]))
            for head in [key]+heads:
                aa=a if head==key else engine.run(head,a['embeddings'])
                bb=b if head==key else engine.run(head,b['embeddings'])
                errors=[float(np.max(np.abs(value-bb[k]))) for k,value in aa.items() if k!='embeddings']
                error=max(errors)
                report['model_comparisons'].append({'audio':name,'model':head,'max_abs':error,'passed':error<=.002})
    report['passed']=all(row['passed'] for row in report['feature_comparisons']+report['model_comparisons'])
    report['scope']='Shared canonical PCM, deterministic silence retained, custom tail coverage. Not official codec/resampling equivalence or recognition accuracy.'
    ms.write_json(out/'reference_results.json',report)
    print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1

if __name__=='__main__': raise SystemExit(main())
