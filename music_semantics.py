"""Optional, local CPU music semantics. SPDX-License-Identifier: AGPL-3.0-or-later.

Model licenses are separate: YAMNet Apache-2.0; the MTG overview declares
CC BY-NC-SA 4.0 with unresolved NoDerivatives text. See LICENSE_STATUS.md.
No model downloads or cloud API.
Scores and status thresholds are uncalibrated; conservative local music gate.
"""
from __future__ import annotations
import ctypes
import hashlib
import html
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import zipfile
os.environ['ORT_DISABLE_TELEMETRY']='1'
import numpy as np
import semantic_frontend as frontend
import music_gate

ROOT = Path(__file__).resolve().parent
SCHEMA = 'music-semantics/1.1'
SETTINGS = {'sample_rate':16000, 'frame_size':512, 'hop_size':256, 'patch_hop':62,
            'effnet_frames':128, 'musicnn_frames':187, 'threads':2, 'batch_size':4,
            'head_threads':1, 'session_spinning':False, 'onnx_telemetry':False,
            'gate_version':music_gate.VERSION,'gate_policy':dict(music_gate.POLICY),
            'window_seconds':10., 'window_hop_seconds':5., 'minimum_seconds':3.,
            'silence_rms':1e-5, 'max_seconds':1800., 'frontend':frontend.FRONTEND_VERSION,
            'decode':'soundfile/native-f32; fallback ffmpeg/local-f32-wav; arithmetic-channel-mean; soxr-HQ',
            'aggregation':'Voronoi cells of patch centers, clipped to duration; exclude near-silent cells'}
POLICY = {'calibrated':False, 'fine_min_score':.55, 'fine_min_margin':.20,
          'fine_min_time_consistency':.70,'coarse_min_score':.10,'coarse_strong_score':.15,
          'coarse_margin':.04,'yamnet_coarse_source_min':.20,
          'mood_min_score':.10, 'voice_min_score':.65,
          'scope':'Candidate display rules only. Not correctness probabilities or out-of-distribution detection.'}
MOODS = {'calm':'平静','dark':'阴暗','dream':'梦幻','emotional':'情绪化','energetic':'有活力',
         'fun':'轻松有趣','happy':'愉快','hopeful':'充满希望','inspiring':'鼓舞',
         'love':'爱意','meditative':'冥想','melancholic':'忧郁','motivational':'激励',
         'positive':'积极','powerful':'有力量','relaxing':'放松','romantic':'浪漫',
         'sad':'悲伤','soft':'柔和','upbeat':'欢快','uplifting':'振奋'}
PARENTS = {'Blues':'蓝调','Brass & Military':'铜管与军乐',"Children's":'儿童音乐',
           'Classical':'古典','Electronic':'电子','Folk, World, & Country':'民谣／世界／乡村',
           'Funk / Soul':'放克／灵魂','Hip Hop':'嘻哈','Jazz':'爵士','Latin':'拉丁',
           'Non-Music':'非音乐（目录标签）','Pop':'流行','Reggae':'雷鬼','Rock':'摇滚',
           'Stage & Screen':'舞台与影视'}
STYLE_ZH = {'Soundtrack':'配乐','Score':'影视配乐','Ambient':'氛围','Downtempo':'缓拍',
            'Ballad':'抒情','Synth-pop':'合成器流行','Indie Pop':'独立流行','Pop Rock':'流行摇滚',
            'Classical':'古典','Contemporary':'当代','Neo-Classical':'新古典','Modern':'现代',
            'Romantic':'浪漫主义','Choral':'合唱','Instrumental':'器乐','Piano Blues':'钢琴蓝调',
            'J-pop':'日本流行','J-Rock':'日本摇滚','Vocal':'声乐','Easy Listening':'轻音乐',
            'Modern Classical':'现代古典','Anison':'动画歌曲'}
WARNINGS = [
    '风格与情绪为模型候选，分数未经概率校准；未通过独立真实标注集的准确率验收。',
    '先用本地YAMNet判断音乐证据；门槛未经大规模校准，困难输入会拒答，也仍可能误判。',
    '细风格支持不足时只给粗分类；门类也不明确时只给有人声音乐／器乐音乐等内容类型。',
    '情绪表示录音听感倾向，不代表听众感受、作者意图或固定故事情节。',
    '人声模型只给有人声／器乐倾向，不能证明正在唱歌或识别歌手。',
    '窗口为10秒上下文、5秒步进；边界近似；整曲汇总按底层片段时长加权。',
    '仅支持模型标签表；国风、二次元等表外概念不自动补造。',
    '完全本地的语义路径不调用在线大模型；将JSON交给在线聊天是另一次数据发送。']

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def fingerprint(path):
    path=Path(path)
    return {'name':path.name,'bytes':path.stat().st_size,'sha256':sha(path)}

def write_json(path, value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def memory():
    if os.name != 'nt':
        import resource
        return {'peak_working_set_bytes':int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*1024}
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in
            ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
             'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
    kernel=ctypes.WinDLL('kernel32'); kernel.GetCurrentProcess.restype=wintypes.HANDLE
    api=ctypes.WinDLL('psapi'); api.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    value=Counters(); value.cb=ctypes.sizeof(value)
    if not api.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(value),value.cb):
        raise OSError('GetProcessMemoryInfo failed')
    return {'working_set_bytes':value.WorkingSetSize,'peak_working_set_bytes':value.PeakWorkingSetSize,
            'private_commit_bytes':value.PagefileUsage,'peak_private_commit_bytes':value.PeakPagefileUsage}

def decode(path):
    """Same channel mean and soxr-HQ for all codecs; no peak normalization."""
    import soundfile as sf
    import soxr
    path=Path(path)
    decoder='soundfile'
    try:
        info=sf.info(str(path))
        if info.duration > SETTINGS['max_seconds']: raise ValueError('语义分析当前限制为30分钟以内')
        y,sr=sf.read(str(path),dtype='float32',always_2d=True)
    except (RuntimeError, sf.LibsndfileError):
        import imageio_ffmpeg
        with tempfile.TemporaryDirectory(prefix='music_semantics_') as tmp:
            wav=Path(tmp)/'decoded.wav'
            proc=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-y','-loglevel','error',
                '-protocol_whitelist','file,pipe','-i',str(path.resolve()),'-vn','-t',str(SETTINGS['max_seconds']+1),
                '-c:a','pcm_f32le',str(wav)],capture_output=True)
            if proc.returncode: raise ValueError('本地音频解码失败：'+proc.stderr.decode('utf-8','replace')[-400:])
            y,sr=sf.read(str(wav),dtype='float32',always_2d=True)
        decoder='local_ffmpeg_pcm_f32le'
    if not y.size or not np.isfinite(y).all(): raise ValueError('音频为空或包含非有限数值')
    if len(y)/sr > SETTINGS['max_seconds']: raise ValueError('语义分析当前限制为30分钟以内')
    channels=y.shape[1]; native_rate=int(sr)
    y=np.mean(y,axis=1,dtype=np.float32)
    if sr != 16000: y=soxr.resample(y,sr,16000,quality='HQ')
    return np.ascontiguousarray(y,np.float32), {'decoder':decoder,'native_sample_rate':native_rate,
        'channels':channels,'channel_mix':'arithmetic_mean','resample':'soxr_HQ' if sr!=16000 else 'none',
        'normalization':'none','pcm_sha256':hashlib.sha256(y.tobytes()).hexdigest()}

def default_models_dir():
    """Optional external model store; source distributions contain no weights."""
    return Path(os.environ.get('MUSIC_SCRIBE_MODELS') or ROOT/'models')


def verify_models(folder):
    manifest_path=ROOT/'models/manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    folder=Path(folder)
    for value in manifest['models'].values():
        for key in ['weights','metadata']:
            record=value[key]; path=folder/record['name']
            if not path.is_file() or path.stat().st_size!=record['bytes'] or sha(path)!=record['sha256']:
                raise ValueError('缺失或指纹不符：'+str(path)+
                    '；运行 python download_models.py --models-dir "'+str(folder)+
                    '" 获取完整语义权重（含 CC BY-NC-SA 4.0 声明及未解决的 ND 文本冲突，见 LICENSE_STATUS.md）；未下载或使用云端替代')
    return manifest, fingerprint(manifest_path)

class Engine:
    """Reused across files only when a caller explicitly keeps this object."""
    def __init__(self, folder=None):
        self.folder=Path(folder) if folder is not None else default_models_dir()
        self.manifest,self.manifest_id=verify_models(self.folder)
        self.sessions={}
    def session(self,key):
        if key not in self.sessions:
            import onnxruntime as ort
            ort.disable_telemetry_events()
            options=ort.SessionOptions()
            options.intra_op_num_threads=2 if key in ('effnet','musicnn','gate') else 1
            options.inter_op_num_threads=1
            options.add_session_config_entry('session.intra_op.allow_spinning','0')
            options.add_session_config_entry('session.inter_op.allow_spinning','0')
            options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
            self.sessions[key]=ort.InferenceSession(str(self.folder/self.manifest['models'][key]['weights']['name']),
                sess_options=options,providers=['CPUExecutionProvider'])
        return self.sessions[key]
    def run(self,key,x):
        session=self.session(key)
        outputs=session.run(None,{session.get_inputs()[0].name:np.ascontiguousarray(x,np.float32)})
        if not all(np.isfinite(v).all() for v in outputs): raise RuntimeError('模型产生非有限输出：'+key)
        return dict(zip((v.name for v in session.get_outputs()),outputs))
    def labels(self,key):
        path=self.folder/self.manifest['models'][key]['metadata']['name']
        return json.loads(path.read_text(encoding='utf-8'))['classes']

def cells(starts,size,duration):
    left=np.maximum(0,(np.asarray(starts)*256-256)/16000)
    right=np.minimum(duration,((np.asarray(starts)+size-1)*256+256)/16000)
    centers=(left+right)/2
    edges=np.r_[0,(centers[:-1]+centers[1:])/2,duration]
    return np.stack([edges[:-1],edges[1:]],axis=1),np.stack([left,right],axis=1)

def infer_audio(y,engine,gate_arrays):
    features=frontend.audio_features(y)
    arrays=dict(gate_arrays)
    for name,size in [('effnet',128),('musicnn',187)]:
        starts=frontend.patches(features,size)
        cell,support=cells(starts,size,len(y)/16000)
        energy=np.array([np.sqrt(np.mean(y[int(a*16000):max(int(a*16000)+1,int(b*16000))].astype(float)**2))
            >SETTINGS['silence_rms'] for a,b in support],bool)
        active=energy & music_gate.context_mask(arrays,support)
        selected=np.flatnonzero(active)
        arrays[name+'_scores']=np.zeros((len(starts),400 if name=='effnet' else 50),np.float32)
        heads=['moodtheme','voice'] if name=='effnet' else ['deam']
        for head in heads: arrays[head+'_scores']=np.zeros((len(starts),56 if head=='moodtheme' else 2),np.float32)
        for i in range(0,len(selected),4):
            indices=selected[i:i+4]
            batch=np.stack([features[starts[j]:starts[j]+size] for j in indices])
            outputs=engine.run(name,batch)
            arrays[name+'_scores'][indices]=outputs['activations']
            for head in heads:
                result=engine.run(head,outputs['embeddings'])
                arrays[head+'_scores'][indices]=next(iter(result.values()))
        arrays[name+'_cells']=cell
        arrays[name+'_support']=support
        arrays[name+'_starts']=np.asarray(starts,np.int64)
        arrays[name+'_energy_active']=energy
        arrays[name+'_active']=active
    return arrays

def validate_arrays(arrays,duration):
    music_gate.validate(arrays,duration)
    music_seconds=float(np.diff(arrays['gate_cells'],axis=1).ravel()[music_gate.music_mask(arrays)].sum())
    if 'effnet_scores' not in arrays:
        if music_seconds+1e-8>=music_gate.POLICY['minimum_music_seconds']: raise ValueError('Missing semantic inference for music evidence')
        return
    expected={'effnet_scores':400,'moodtheme_scores':56,'voice_scores':2,'musicnn_scores':50,'deam_scores':2}
    for group in ['effnet','musicnn']:
        starts=arrays[group+'_starts']; cell=arrays[group+'_cells']; support=arrays[group+'_support']; active=arrays[group+'_active']
        if starts.ndim!=1 or not len(starts) or starts.dtype.kind not in 'iu' or starts[0]!=0 or np.any(np.diff(starts)<=0):
            raise ValueError('Invalid cached patch starts')
        if cell.shape!=(len(starts),2) or support.shape!=cell.shape or active.shape!=starts.shape or active.dtype!=bool:
            raise ValueError('Invalid cached intervals')
        if not np.isfinite(cell).all() or not np.isfinite(support).all() or not np.all(cell[:,1]>cell[:,0]):
            raise ValueError('Invalid cached time values')
        if abs(cell[0,0])>1e-8 or abs(cell[-1,1]-duration)>1e-8 or not np.allclose(cell[:-1,1],cell[1:,0],atol=1e-8):
            raise ValueError('Cached coverage is incomplete')
        if np.any(support<0) or np.any(support>duration+1e-8) or np.any(support[:,1]<=support[:,0]):
            raise ValueError('Invalid cached patch support')
        energy=arrays[group+'_energy_active']
        if energy.shape!=active.shape or energy.dtype!=bool or not np.array_equal(active,energy & music_gate.context_mask(arrays,support)):
            raise ValueError('Semantic mask differs from energy/music context gate')
    for key,width in expected.items():
        rows=len(arrays[('musicnn' if key.startswith(('musicnn','deam')) else 'effnet')+'_starts'])
        value=arrays[key]
        if value.shape!=(rows,width) or value.dtype!=np.float32 or not np.isfinite(value).all():
            raise ValueError('Invalid cached scores: '+key)
        group='musicnn' if key in ('musicnn_scores','deam_scores') else 'effnet'
        if np.any(value[~arrays[group+'_active']]!=0): raise ValueError('Non-evaluated semantic rows must be explicit zero placeholders')

def cache_key(source,manifest,code):
    return hashlib.sha256(json.dumps({'source':source,'models':manifest,'code':code,'settings':SETTINGS},
        sort_keys=True).encode()).hexdigest()

def read_cache(folder,key,duration):
    try:
        path=Path(folder)/(key+'.npz'); info=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
        if info['key']!=key or path.stat().st_size>32*1024*1024 or sha(path)!=info['sha256']: return None
        with np.load(path,allow_pickle=False) as data: arrays={k:data[k] for k in data.files}
        validate_arrays(arrays,duration)
        return arrays
    except (OSError,ValueError,KeyError,EOFError,zipfile.BadZipFile): return None

def save_cache(folder,key,arrays):
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=folder,suffix='.npz',delete=False) as stream:
        temp=Path(stream.name)
        np.savez_compressed(stream,**arrays)
    try:
        path=folder/(key+'.npz'); temp.replace(path)
        info={'key':key,'sha256':sha(path)}
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=folder,suffix='.json',delete=False) as stream:
            json.dump(info,stream); meta=Path(stream.name)
        meta.replace(path.with_suffix('.json'))
    finally: temp.unlink(missing_ok=True)

def weighted(arrays,key,t0,t1):
    group='musicnn' if key in ('musicnn','deam') else 'effnet'
    cell=arrays[group+'_cells']; active=arrays[group+'_active']
    weights=music_gate.overlap_weights(arrays,cell,t0,t1)*active
    indices=np.flatnonzero(weights>0)
    if not len(indices): return None,0.,[]
    return np.average(arrays[key+'_scores'],axis=0,weights=weights),float(weights.sum()),[f'{group}_{i:05d}' for i in indices]

def top(scores,labels,indices=None,n=3):
    indices=list(range(len(labels))) if indices is None else list(indices)
    indices.sort(key=lambda i:(-float(scores[i]),i))
    return [{'label':labels[i],'display_zh':MOODS.get(labels[i],STYLE_ZH.get(labels[i],labels[i])),
             'score':float(scores[i]),'index':i} for i in indices[:n]]

def describe(arrays,labels,t0,t1):
    presence=music_gate.describe(arrays,labels['gate'],t0,t1)
    base={'t0':t0,'t1':t1,'status':'insufficient_evidence','music_presence':presence,
          'active_seconds':0.,'support_patch_ids':[],'axis_patch_ids':[]}
    if not presence['semantics_allowed']:
        base['status']='not_music' if presence['status']=='non_music' else 'uncertain_input'
        base['reason']='music_evidence_gate_blocked'; return base
    genre,coverage,ids=weighted(arrays,'effnet',t0,t1)
    axis,axis_coverage,axis_ids=weighted(arrays,'deam',t0,t1)
    base.update(active_seconds=coverage,support_patch_ids=ids,axis_patch_ids=axis_ids)
    if genre is None or min(coverage,axis_coverage)+1e-8<SETTINGS['minimum_seconds']:
        # Music itself is supported by the independent gate, while the longer
        # semantic model contexts may straddle silence/non-music. Keep only a
        # coarse content class; do not invent an emotion or a fine genre.
        evidence=music_gate.coarse_evidence(arrays,labels['gate'],t0,t1)
        coarse=[{'label':p,'display_zh':PARENTS[p],'score':s,'source':'yamnet_genre_max'}
                for p,s in sorted(evidence.items(),key=lambda item:-item[1]) if s>=POLICY['yamnet_coarse_source_min']][:3]
        if not coarse:
            coarse=[{'label':'Music','display_zh':'音乐，门类不明确','score':None,'source':'music_presence_only','kind':'content_type_not_genre'}]
        base.update(status='ambiguous',reason='insufficient_music_context_for_detailed_semantics',
            styles={'status':'ambiguous','level':'coarse','candidates':coarse,'parent_genres':[],
                    'fine_status':'suppressed','fallback_reason':'insufficient_semantic_context'})
        return base
    fine_styles=top(genre,labels['effnet'])
    for item in fine_styles:
        parent,_,style=item['label'].partition('---')
        item['display_zh']=PARENTS.get(parent,parent)+'／'+STYLE_ZH.get(style,style)
        item['parent_label']=parent
    parents={}
    for i,label in enumerate(labels['effnet']):
        parent=label.split('---')[0]; parents[parent]=max(parents.get(parent,0.),float(genre[i]))
    parent_rows=[{'label':p,'display_zh':PARENTS.get(p,p),'score':v,'aggregation':'max_child_score_not_probability'}
        for p,v in sorted(parents.items(),key=lambda item:-item[1]) if p in music_gate.COARSE_MAP][:3]
    mood,_,_=weighted(arrays,'moodtheme',t0,t1); voice,_,_=weighted(arrays,'voice',t0,t1)
    mood_indices=[i for i,label in enumerate(labels['moodtheme']) if label in MOODS]
    themes=[i for i,label in enumerate(labels['moodtheme']) if label not in MOODS]
    moods=top(mood,labels['moodtheme'],mood_indices)
    types=top(voice,labels['voice'],n=2)
    for item in types: item['display_zh']='器乐倾向' if item['label']=='instrumental' else '有人声倾向'
    axis_raw={'valence':float(axis[0]),'arousal':float(axis[1]),'reference_scale':[1,9],
              'scale_kind':'training_annotation_range_not_probability',
              'out_of_reference_range':bool(np.any((axis<1)|(axis>9))),
              'status':'candidate'}
    conflicts=[]
    # Descriptive disagreements retained; neutral axes do not force happy/sad.
    if moods[0]['score']>=.10:
        if moods[0]['label'] in ('happy','positive','upbeat') and axis[0]<4: conflicts.append('positive_tag_vs_low_valence')
        if moods[0]['label'] in ('sad','melancholic','dark') and axis[0]>6: conflicts.append('negative_tag_vs_high_valence')
        if moods[0]['label'] in ('calm','relaxing','meditative') and axis[1]>6: conflicts.append('calm_tag_vs_high_arousal')
    coarse_source='discogs_parent_max'
    gate_coarse=music_gate.coarse_evidence(arrays,labels['gate'],t0,t1)
    if gate_coarse and max(gate_coarse.values())>=POLICY['yamnet_coarse_source_min']:
        coarse_source='yamnet_genre_max'
        coarse_rows=[{'label':p,'display_zh':PARENTS[p],'score':v,'aggregation':'max_child_score_not_probability'}
            for p,v in sorted(gate_coarse.items(),key=lambda item:-item[1])[:3]]
    else: coarse_rows=parent_rows
    coarse=[dict(row,source=coarse_source) for row in coarse_rows if row['score']>=POLICY['coarse_min_score']]
    coarse_clear=bool(coarse and coarse[0]['score']>=POLICY['coarse_strong_score'] and
        (len(coarse)<2 or coarse[0]['score']-coarse[1]['score']>=POLICY['coarse_margin']))
    if coarse_clear: coarse=coarse[:1]
    if not coarse:
        label='Vocal music' if types[0]['label']=='voice' else 'Instrumental music'
        display='有人声音乐' if types[0]['label']=='voice' else '器乐音乐'
        if types[0]['score']<POLICY['voice_min_score']: label='Music'; display='音乐，门类不明确'
        coarse=[{'label':label,'display_zh':display,'score':types[0]['score'] if label!='Music' else None,
                 'source':'voice_type' if label!='Music' else 'music_presence_only','kind':'content_type_not_genre'}]
    weight=music_gate.overlap_weights(arrays,arrays['effnet_cells'],t0,t1)*arrays['effnet_active']
    first=fine_styles[0]
    consistency=float(weight[np.argmax(arrays['effnet_scores'],axis=1)==first['index']].sum()/weight.sum())
    fine_allowed=bool(coarse_clear and first['parent_label']==coarse[0]['label'] and
        first['score']>=POLICY['fine_min_score'] and first['score']-fine_styles[1]['score']>=POLICY['fine_min_margin'] and
        consistency>=POLICY['fine_min_time_consistency'])
    styles=fine_styles[:1] if fine_allowed else coarse
    genre_status='candidate' if fine_allowed or coarse_clear else 'ambiguous'
    mood_status='candidate' if moods[0]['score']>=.10 else 'ambiguous'
    type_status='candidate' if types[0]['score']>=.65 else 'ambiguous'
    base.update(status='candidate' if all(s=='candidate' for s in [genre_status,mood_status,type_status]) and not conflicts else 'ambiguous',
        styles={'status':genre_status,'level':'fine' if fine_allowed else 'coarse','candidates':styles,'parent_genres':parent_rows,
                'fine_status':'candidate' if fine_allowed else 'suppressed',
                'fallback_reason':None if fine_allowed else 'insufficient_fine_score_margin_consistency_or_parent_agreement',
                'fine_time_consistency':consistency},
        mood={'status':mood_status,'candidates':moods},themes={'status':'candidate','candidates':top(mood,labels['moodtheme'],themes),
        'meaning':'Similarity to dataset theme labels; not known purpose or provenance.'},
        voice_type={'status':type_status,'candidates':types},affect=axis_raw,disagreements=conflicts)
    return base

def summary_text(value):
    if 'styles' not in value:
        if value.get('status')=='not_music': return '判断为非音乐或以非音乐声音为主，未运行音乐风格、类型和情绪分类。'
        if value.get('status')=='uncertain_input': return '未获得足够可靠的音乐证据，暂不输出音乐风格、类型和情绪。'
        return '可用音乐支持不足3秒，未输出风格、类型或情绪候选。'
    style='、'.join(i['display_zh']+(f' {i["score"]:.3f}' if i.get('score') is not None else '') for i in value['styles']['candidates'])
    if 'affect' not in value:
        return f'粗分类候选（细风格未确定）：{style}。可靠音乐上下文不足，未给出情绪、二维情感和人声类型判断。'
    mood='、'.join(f'{i["display_zh"]} {i["score"]:.3f}' for i in value['mood']['candidates'])
    a=value['affect']
    scope='仅对检出的音乐片段汇总。' if value['music_presence']['status']=='mixed' else ''
    level='细风格候选' if value['styles']['level']=='fine' else '粗分类候选（细风格未确定）'
    return (scope+f'{level}：{style}（{value["styles"]["status"]}）。类型：{value["voice_type"]["candidates"][0]["display_zh"]}'
        f'（{value["voice_type"]["status"]}，分数 {value["voice_type"]["candidates"][0]["score"]:.3f}）。'
        f'情绪候选：{mood}（{value["mood"]["status"]}）。'
        f'正负向感 {a["valence"]:.2f}、唤醒程度 {a["arousal"]:.2f}，训练参考刻度1–9。'
        '分数不是概率。以上为未经校准的听感估计，不代表作者意图。')

def unavailable(reason):
    return {'schema_version':SCHEMA,'status':'unavailable','reason':str(reason),'warnings':WARNINGS}

def analyze(path,out,models_dir=None,cache_dir=None,engine=None):
    started=time.perf_counter(); cpu=time.process_time(); initial_memory=memory()
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    path=Path(path)
    if not path.is_file(): raise ValueError('输入必须为已有的本地音频文件')
    source=dict(fingerprint(path),path=str(path.resolve()))
    code={name:fingerprint(ROOT/name) for name in ['music_semantics.py','semantic_frontend.py','music_gate.py']}
    timings={}; step=time.perf_counter()
    try:
        if engine is None: engine=Engine(models_dir if models_dir is not None else default_models_dir())
        else: verify_models(engine.folder)
    except (ValueError,OSError) as exc:
        doc=unavailable(exc); doc['source']=source; write_json(out/'semantics.json',doc); render_html(doc,out); return doc
    timings['verify_models']=time.perf_counter()-step
    step=time.perf_counter(); y,decoder=decode(path); duration=len(y)/16000
    timings['decode_resample']=time.perf_counter()-step
    rms=float(np.sqrt(np.mean(y.astype(float)**2)))
    doc={'schema_version':SCHEMA,'tool_version':'1.3.0','source':source,'duration':duration,
         'status':'insufficient_evidence','settings':dict(SETTINGS),'policy':dict(POLICY),
         'warnings':list(WARNINGS),'provenance':{'code':code,'model_manifest':engine.manifest_id,
             'frontend_validation':fingerprint(ROOT/'FRONTEND_VALIDATION.json'),
             'models':engine.manifest['models'],'decoder':decoder,'provider':'CPUExecutionProvider',
             'external_network':'No downloader, remote API or telemetry implemented in this semantic path.'},
         'signal_rms':rms,'music_presence':{'status':'insufficient_evidence','reason':'not_run_short_or_near_silence'},
         'unsupported_concepts':['国风','二次元','作者意图','曲名','歌手身份'],
         'unsupported_label_status':'unsupported_label','cache':{'enabled':cache_dir is not None,'hit':False},
         'windows':[],'patches':[],'gate_patches':[]}
    if (ROOT/'POLICY_LOCK.json').is_file():
        doc['provenance']['policy_lock']=fingerprint(ROOT/'POLICY_LOCK.json')
    if duration<3 or rms<=SETTINGS['silence_rms']:
        doc['global']={'status':'insufficient_evidence','reason':'too_short_or_near_digital_silence','t0':0.,'t1':duration}
    else:
        key=cache_key(source['sha256'],engine.manifest_id,code); step=time.perf_counter()
        arrays=read_cache(cache_dir,key,duration) if cache_dir else None
        doc['cache'].update(key=key,hit=arrays is not None)
        if arrays is None:
            gate_step=time.perf_counter(); arrays=music_gate.infer(y,engine)
            timings['music_gate']=time.perf_counter()-gate_step
            presence=music_gate.describe(arrays,engine.labels('gate'),0.,duration)
            if presence['semantics_allowed']: arrays=infer_audio(y,engine,arrays)
            validate_arrays(arrays,duration)
            if cache_dir:
                try: save_cache(cache_dir,key,arrays)
                except OSError as exc: doc['warnings'].append('缓存未写入，分析仍有效：'+str(exc))
        timings['frontend_and_inference_or_cache']=time.perf_counter()-step
        evidence=out/'semantics_scores.npz'; np.savez_compressed(evidence,**arrays)
        doc['raw_evidence']=fingerprint(evidence)
        labels={k:engine.labels(k) for k in (['gate','effnet','moodtheme','voice','musicnn','deam'] if 'effnet_scores' in arrays else ['gate'])}; doc['labels']=labels
        doc['global']=describe(arrays,labels,0.,duration); doc['status']=doc['global']['status']
        doc['music_presence']=doc['global']['music_presence']
        doc['classification_ran']='effnet_scores' in arrays
        # One short final window remains explicit; it may be insufficient evidence.
        for i,t0 in enumerate(np.arange(0,duration,5.)):
            window=describe(arrays,labels,float(t0),min(duration,float(t0)+10.)); window['id']=f'w{i:05d}'
            doc['windows'].append(window)
        for group in (['effnet','musicnn'] if 'effnet_scores' in arrays else []):
            for i,((t0,t1),(s0,s1),active) in enumerate(zip(arrays[group+'_cells'],arrays[group+'_support'],arrays[group+'_active'])):
                doc['patches'].append({'id':f'{group}_{i:05d}','array_row':i,'model':group,'t0':float(t0),'t1':float(t1),
                    'context_t0':float(s0),'context_t1':float(s1),'active':bool(active)})
        gate_mask=music_gate.music_mask(arrays)
        for i,((t0,t1),(s0,s1)) in enumerate(zip(arrays['gate_cells'],arrays['gate_support'])):
            doc['gate_patches'].append({'id':f'g{i:05d}','array_row':i,'t0':float(t0),'t1':float(t1),
                'context_t0':float(s0),'context_t1':float(s1),'music_supported':bool(gate_mask[i])})
        doc['coverage']={'mode':'all_audio_gated_music_only_classification','duration_seconds':duration,
            'active_effnet_seconds':doc['global']['active_seconds'],
            'accepted_music_seconds':doc['music_presence']['music_seconds'],
            'note':'Full-audio gate scan; music semantics use only supported contexts and music-cell duration weights. Zero score placeholders mark uncomputed rows.'}
    doc['summary_zh']=summary_text(doc['global'])
    doc['timings_seconds']=timings
    timings['total_before_report']=time.perf_counter()-started
    doc['resources']={'process_cpu_seconds':time.process_time()-cpu,'memory_before':initial_memory,'memory_after':memory(),
        'memory_scope':'Whole-process lifetime high-water mark; not isolated model allocation or subprocess peak.'}
    write_json(out/'semantics.json',doc); render_html(doc,out)
    return doc

def compact(doc):
    result={k:doc[k] for k in ('schema_version','tool_version','source','duration','status','global','summary_zh',
        'coverage','raw_evidence','warnings','timings_seconds','resources','cache','reason','music_presence',
        'unsupported_concepts','unsupported_label_status','policy') if k in doc}
    if 'global' in result:
        result['global']={k:v for k,v in doc['global'].items() if k not in ('support_patch_ids','axis_patch_ids')}
        for key in ['support_patch_ids','axis_patch_ids']:
            if key in doc['global']: result['global'][key+'_count']=len(doc['global'][key])
        if 'music_presence' in result['global']:
            result['global']['music_presence']={k:v for k,v in result['global']['music_presence'].items() if k!='support_patch_ids'}
    if isinstance(result.get('music_presence'),dict):
        result['music_presence']={k:v for k,v in result['music_presence'].items() if k!='support_patch_ids'}
    if 'classification_ran' in doc: result['classification_ran']=doc['classification_ran']
    return result

def render_html(doc,out):
    esc=lambda x:html.escape(str(x))
    rows=[]
    for w in doc.get('windows',[]):
        rows.append(f'<tr><td>{w["t0"]:.1f}–{w["t1"]:.1f}s</td><td>{esc(summary_text(w))}</td><td>{esc(w["status"])}</td></tr>')
    warnings=''.join('<li>'+esc(w)+'</li>' for w in doc['warnings'])
    points=[w for w in doc.get('windows',[]) if 'affect' in w]
    chart=''
    if points:
        low=min(1.,min(min(w['affect'][a] for a in ('valence','arousal')) for w in points))
        high=max(9.,max(max(w['affect'][a] for a in ('valence','arousal')) for w in points))
        lines=[]
        groups=[]
        for w in points:
            if not groups or w['t0']-groups[-1][-1]['t0']>5.001: groups.append([])
            groups[-1].append(w)
        for name,color in [('valence','#336b87'),('arousal','#ad5c31')]:
            for group in groups:
                coords=' '.join(f'{50+(w["t0"]+w["t1"])/2/doc["duration"]*880:.2f},{210-(w["affect"][name]-low)/(high-low)*170:.2f}' for w in group)
                lines.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2"/>')
        chart=f'<section><h2>二维听感趋势</h2><p>蓝：正负向感；棕：唤醒程度。训练参考刻度1–9；窗口估计，未经人工情感标注验证。</p><svg viewBox="0 0 960 260" role="img" aria-label="正负向感与唤醒程度随原音频时间变化"><path d="M50 30V220H930" fill="none" stroke="#999"/><text x="8" y="45">{high:.1f}</text><text x="8" y="215">{low:.1f}</text><text x="50" y="248">0s</text><text x="860" y="248">{doc["duration"]:.1f}s</text>{"".join(lines)}</svg></section>'
    page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>音乐风格与情感候选</title><style>body{{font:16px/1.7 system-ui;background:#f0eee8;color:#242424;margin:0}}
main{{max-width:1050px;margin:auto;padding:28px}}section{{background:#fffdf8;padding:22px;margin:16px 0;border:1px solid #ddd7ca}}
td,th{{text-align:left;padding:10px;border-bottom:1px solid #ddd;vertical-align:top}}table{{width:100%;border-collapse:collapse}}
a{{color:#315d77}}</style><main><h1>音乐风格、类型与情感候选</h1><p>{esc(doc.get('source',{}).get('name',''))} · {esc(doc['status'])}</p>
<section><p>{esc(doc.get('summary_zh',doc.get('reason','')))}</p><p>原始分数、歧义状态和来源见 <a href="semantics.json">semantics.json</a>。</p></section>
<section><h2>限制</h2><ul>{warnings}</ul></section>{chart}<section><h2>原音频时间轴</h2><table><tr><th>时间</th><th>候选听感</th><th>状态</th></tr>{''.join(rows)}</table></section></main></html>'''
    (Path(out)/'semantics.html').write_text(page,encoding='utf-8')

def query(doc,folder,t0,t1):
    if doc.get('schema_version')!=SCHEMA: raise ValueError('不支持的语义schema')
    # Canonical 16-kHz and transcription 22.05-kHz resampling can differ by one sample.
    if not np.isfinite([t0,t1]).all() or not 0<=t0<min(t1,doc.get('duration',0)) or t1>doc.get('duration',0)+1/16000:
        raise ValueError('查询秒数超出范围')
    local_decision=None
    if 'raw_evidence' in doc:
        info=doc['raw_evidence']; path=(Path(folder)/info['name']).resolve()
        if path.parent!=Path(folder).resolve() or fingerprint(path)!=info: raise ValueError('语义分数文件路径或指纹不符')
        if path.stat().st_size>32*1024*1024: raise ValueError('语义证据文件超过大小限制')
        if doc.get('settings',{}).get('gate_policy',music_gate.POLICY)!=music_gate.POLICY:
            raise ValueError('门控策略不匹配，请使用生成证据的同一副本查询')
        with np.load(path,allow_pickle=False) as data: arrays={key:data[key] for key in data.files}
        validate_arrays(arrays,doc['duration'])
        local_decision=describe(arrays,doc['labels'],t0,min(t1,doc['duration']))
    visible=local_decision is not None and local_decision['music_presence']['semantics_allowed']
    selected=[w for w in doc.get('windows',[]) if w['t0']<t1 and w['t1']>t0]
    return {'schema_version':SCHEMA,'query':{'t0':t0,'t1':t1,'unit':'seconds'},'source':doc['source'],
            'decision':local_decision,'global':compact(doc).get('global') if visible else None,
            'windows':selected if visible else [],
            'withheld_window_contexts':[] if visible else [{'id':w['id'],'t0':w['t0'],'t1':w['t1'],
                'reason':'query_interval_has_insufficient_music_evidence'} for w in selected],
            'patches':[p for p in doc.get('patches',[]) if p['t0']<t1 and p['t1']>t0],
            'gate_patches':[p for p in doc.get('gate_patches',[]) if p['t0']<t1 and p['t1']>t0],
            'raw_evidence':doc.get('raw_evidence'),'warnings':doc['warnings']}
