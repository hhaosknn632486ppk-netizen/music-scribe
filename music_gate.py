"""Local YAMNet evidence gate. No network or extra runtime dependency.

Google YAMNet (Apache-2.0), Rockchip supplied ONNX export with embedded DSP.
Uncalibrated conservative rules, not a guarantee of music/non-music truth.
"""
import numpy as np

VERSION='yamnet-music-gate/1'
POLICY={'calibrated':False,'music_score_min':.50,'low_music_max':.10,
        'minimum_music_run_seconds':1.0,'minimum_music_seconds':3.0,
        'context_music_ratio_min':.60,'minimum_context_real_seconds':.48,
        'mixed_music_ratio_below':.80,'non_music_alternative_min':.20,
        'scope':'Frozen on development examples only. AudioSet activations are not calibrated correctness probabilities.'}
COARSE_MAP={
    'Pop':['Pop music'],'Hip Hop':['Hip hop music','Rapping','Beatboxing'],
    'Rock':['Rock music','Heavy metal','Punk rock','Grunge','Progressive rock','Rock and roll','Psychedelic rock'],
    'Funk / Soul':['Funk','Soul music','Rhythm and blues'], 'Reggae':['Reggae','Ska'],
    'Folk, World, & Country':['Country','Folk music','Bluegrass','Traditional music','Music of Asia','Music of Africa','Middle Eastern music'],
    'Jazz':['Jazz','Swing music'],'Classical':['Classical music','Opera'],
    'Electronic':['Electronic music','Electronica','Electronic dance music','House music','Techno','Dubstep','Drum and bass','Ambient music','Trance music'],
    'Latin':['Music of Latin America','Salsa music','Flamenco'],'Blues':['Blues']}

def infer(y,engine):
    duration=len(y)/16000; scores=[]; cells=[]; contexts=[]; reliable=[]
    for start in range(0,len(y),48000):
        chunk=y[start:start+48000]; length=len(chunk); seconds=length/16000
        values=engine.session('gate').run(['scores'],{'new_input':np.pad(chunk,(0,48000-length))[None,:].astype(np.float32)})[0]
        if values.shape!=(6,521) or not np.isfinite(values).all(): raise ValueError('Invalid YAMNet output')
        left=np.arange(6)*.48
        keep=left<seconds
        left=left[keep]; right=np.minimum(left+.975,seconds)
        centers=(left+right)/2
        edges=np.r_[0.,(centers[:-1]+centers[1:])/2,seconds]
        scores.extend(values[keep]); cells.extend(np.stack([edges[:-1],edges[1:]],axis=1)+start/16000)
        contexts.extend(np.stack([left,right],axis=1)+start/16000)
        reliable.extend(right-left>=POLICY['minimum_context_real_seconds'])
    arrays={'gate_scores':np.asarray(scores,np.float32),'gate_cells':np.asarray(cells,np.float64),
            'gate_support':np.asarray(contexts,np.float64),'gate_reliable':np.asarray(reliable,bool)}
    validate(arrays,duration)
    return arrays

def validate(a,duration):
    score=a['gate_scores']; cell=a['gate_cells']; support=a['gate_support']; reliable=a['gate_reliable']
    if score.ndim!=2 or score.shape[1]!=521 or score.dtype!=np.float32 or not len(score) or not np.isfinite(score).all():
        raise ValueError('Invalid gate scores')
    if np.any(score<0) or np.any(score>1): raise ValueError('Gate activations outside sigmoid range')
    if cell.shape!=(len(score),2) or support.shape!=cell.shape or reliable.shape!=(len(score),) or reliable.dtype!=bool:
        raise ValueError('Invalid gate array shapes')
    if not np.isfinite(cell).all() or not np.isfinite(support).all() or not np.all(cell[:,1]>cell[:,0]): raise ValueError('Invalid gate timing')
    if abs(cell[0,0])>1e-8 or abs(cell[-1,1]-duration)>1e-8 or not np.allclose(cell[:-1,1],cell[1:,0],rtol=0,atol=1e-8):
        raise ValueError('Incomplete gate coverage')
    if np.any(support<0) or np.any(support>duration+1e-8) or not np.all(support[:,1]>support[:,0]): raise ValueError('Invalid gate context')

def music_mask(a):
    mask=(a['gate_scores'][:,132]>=POLICY['music_score_min']) & a['gate_reliable']
    # Isolated short peaks do not grant permission to infer music semantics.
    changes=np.diff(np.r_[False,mask,False].astype(int)); starts=np.flatnonzero(changes==1); ends=np.flatnonzero(changes==-1)
    cell=a['gate_cells']
    for start,end in zip(starts,ends):
        if cell[end-1,1]-cell[start,0]+1e-8<POLICY['minimum_music_run_seconds']: mask[start:end]=False
    return mask

def overlap_weights(a,intervals,t0=None,t1=None):
    cells=a['gate_cells'][music_mask(a)]
    intervals=np.asarray(intervals)
    left=intervals[:,0] if t0 is None else np.maximum(intervals[:,0],t0)
    right=intervals[:,1] if t1 is None else np.minimum(intervals[:,1],t1)
    weights=np.zeros(len(intervals),float)
    for start,end in cells:
        weights+=np.maximum(0,np.minimum(right,end)-np.maximum(left,start))
    return weights

def context_mask(a,contexts):
    durations=contexts[:,1]-contexts[:,0]
    return overlap_weights(a,contexts)/durations>=POLICY['context_music_ratio_min']

def describe(a,labels,t0,t1):
    cell=a['gate_cells']; w=np.maximum(0,np.minimum(cell[:,1],t1)-np.maximum(cell[:,0],t0))
    indices=np.flatnonzero(w>0)
    mean=np.average(a['gate_scores'],axis=0,weights=w)
    music=music_mask(a); seconds=float(w[music].sum()); fraction=seconds/(t1-t0)
    top=np.argsort(-mean,kind='stable')[:5]
    alt=max(float(mean[i]) for i in range(521) if i!=132)
    if seconds+1e-8>=POLICY['minimum_music_seconds']:
        status='mixed' if fraction<POLICY['mixed_music_ratio_below'] or mean[0]>=.5 else 'music'
    elif mean[132]<=POLICY['low_music_max'] and seconds==0 and alt>=POLICY['non_music_alternative_min']:
        status='non_music'
    else: status='uncertain'
    return {'status':status,'music_seconds':seconds,'music_ratio':fraction,'music_score':float(mean[132]),
        'speech_score':float(mean[0]),'top_events':[{'label':labels[i],'index':int(i),'score':float(mean[i])} for i in top],
        'support_patch_ids':[f'g{i:05d}' for i in indices],'semantics_allowed':status in ('music','mixed'),
        'calibrated':False,'time_reference':'original_audio_seconds','score_kind':'uncalibrated_AudioSet_activation'}

def coarse_evidence(a,labels,t0,t1):
    cell=a['gate_cells']; w=np.maximum(0,np.minimum(cell[:,1],t1)-np.maximum(cell[:,0],t0))*music_mask(a)
    if not w.sum(): return {}
    mean=np.average(a['gate_scores'],axis=0,weights=w)
    return {parent:max(float(mean[labels.index(label)]) for label in children) for parent,children in COARSE_MAP.items()}
