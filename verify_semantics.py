"""Verify current-code/model pairing, raw scores and all derived summaries.

Consistency verification does not establish musical correctness or authenticity.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import music_semantics as ms

def verify(folder, models_dir=None):
    folder=Path(folder).resolve()
    doc=json.loads((folder/'semantics.json').read_text(encoding='utf-8'))
    if doc['schema_version']!=ms.SCHEMA: raise ValueError('Unsupported schema')
    if doc['status']=='unavailable': return {'status':'unavailable','reason':doc['reason']}
    for name,info in doc['provenance']['code'].items():
        if (ms.ROOT/name).resolve().parent!=ms.ROOT or ms.fingerprint(ms.ROOT/name)!=info:
            raise ValueError('Code fingerprint differs: '+name)
    if doc['provenance']['frontend_validation']!=ms.fingerprint(ms.ROOT/'FRONTEND_VALIDATION.json'):
        raise ValueError('Frontend validation file differs')
    if 'policy_lock' in doc['provenance'] and doc['provenance']['policy_lock']!=ms.fingerprint(ms.ROOT/'POLICY_LOCK.json'):
        raise ValueError('Frozen policy record differs')
    validation=json.loads((ms.ROOT/'FRONTEND_VALIDATION.json').read_text(encoding='utf-8'))
    if not validation['passed'] or validation['candidate_frontend_sha256']!=ms.sha(ms.ROOT/'semantic_frontend.py'):
        raise ValueError('Frontend validation does not match candidate code')
    models_dir=Path(models_dir) if models_dir is not None else ms.default_models_dir()
    manifest,manifest_id=ms.verify_models(models_dir)
    if manifest_id!=doc['provenance']['model_manifest'] or manifest['models']!=doc['provenance']['models']:
        raise ValueError('Model provenance differs')
    if doc['policy']!=ms.POLICY or doc['settings']!=ms.SETTINGS: raise ValueError('Policy/settings differ')
    result={'status':'PASS','scope':'Output consistency, not recognition accuracy','source_sha256':doc['source']['sha256'],
        'raw_scores':'not_applicable','windows':len(doc['windows'])}
    duration=doc['duration']
    if not np.isfinite(duration) or duration<=0 or doc['global']['t0']!=0 or doc['global']['t1']!=duration:
        raise ValueError('Invalid duration or global interval')
    if 'raw_evidence' not in doc:
        if doc['global']['status']!='insufficient_evidence' or doc['windows'] or doc['patches']:
            raise ValueError('Missing scores for populated analysis')
        return result
    info=doc['raw_evidence']; path=(folder/info['name']).resolve()
    if path.parent!=folder or ms.fingerprint(path)!=info: raise ValueError('Raw evidence pairing differs')
    with np.load(path,allow_pickle=False) as data: arrays={key:data[key] for key in data.files}
    ms.validate_arrays(arrays,duration)
    engine=ms.Engine(models_dir)
    for key,labels in doc['labels'].items():
        if labels!=engine.labels(key): raise ValueError('Wrong label order: '+key)
    if ms.describe(arrays,doc['labels'],0.,duration)!=doc['global']:
        raise ValueError('Global aggregation differs from raw evidence')
    if doc['summary_zh']!=ms.summary_text(doc['global']): raise ValueError('Summary text differs')
    if len(doc['windows'])!=int(np.ceil(duration/5)): raise ValueError('Incomplete window timeline')
    for i,window in enumerate(doc['windows']):
        expected=ms.describe(arrays,doc['labels'],i*5.,min(duration,i*5.+10.)); expected['id']=f'w{i:05d}'
        if expected!=window: raise ValueError('Window differs from raw evidence: '+str(i))
    for patch in doc['patches']:
        group=patch['model']; row=patch['array_row']
        if patch['id']!=f'{group}_{row:05d}' or [patch['t0'],patch['t1']]!=list(arrays[group+'_cells'][row]):
            raise ValueError('Patch timing differs')
        if [patch['context_t0'],patch['context_t1']]!=list(arrays[group+'_support'][row]) or patch['active']!=bool(arrays[group+'_active'][row]):
            raise ValueError('Patch context differs')
    groups=['effnet','musicnn'] if 'effnet_scores' in arrays else []
    if len(doc['patches'])!=sum(len(arrays[group+'_starts']) for group in groups):
        raise ValueError('Missing patch metadata')
    if doc['music_presence']!=doc['global']['music_presence'] or doc['classification_ran']!=bool(groups):
        raise ValueError('Gate/classification status differs')
    gate_mask=ms.music_gate.music_mask(arrays)
    if len(doc['gate_patches'])!=len(gate_mask): raise ValueError('Incomplete gate patch metadata')
    for i,p in enumerate(doc['gate_patches']):
        if p['id']!=f'g{i:05d}' or p['array_row']!=i or [p['t0'],p['t1']]!=list(arrays['gate_cells'][i]):
            raise ValueError('Gate patch time differs')
        if [p['context_t0'],p['context_t1']]!=list(arrays['gate_support'][i]) or p['music_supported']!=bool(gate_mask[i]):
            raise ValueError('Gate patch support differs')
    if not doc['music_presence']['semantics_allowed'] and ('styles' in doc['global'] or doc['classification_ran']):
        raise ValueError('Blocked input leaked a music style or ran music classifiers')
    result['raw_scores']='PASS'; result['patches']=len(doc['patches'])
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('folder',type=Path)
    parser.add_argument('--models-dir',type=Path,help='Same local model directory used for analysis')
    args=parser.parse_args()
    try: print(json.dumps(verify(args.folder,args.models_dir),ensure_ascii=False))
    except (OSError,ValueError,KeyError) as exc: parser.exit(1,'Verification failed: '+str(exc)+'\n')
