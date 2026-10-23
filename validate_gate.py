"""Check exported DSP against independent NumPy/SciPy official parameters.

This is not TensorFlow/ONNX end-to-end equivalence or recognition accuracy.
Google installation test top-10 expectations are also exercised.
"""
import json
from pathlib import Path
import numpy as np
from scipy.fft import rfft
import music_semantics as ms

def reference_mel(y):
    target=15600+int(np.ceil(max(0,len(y)-15600)/7680))*7680
    y=np.pad(y,(0,target-len(y)))
    frames=np.lib.stride_tricks.sliding_window_view(y,400)[::160]
    window=(.5-.5*np.cos(2*np.pi*np.arange(400)/400)).astype(np.float32)
    spectrum=np.abs(rfft(frames*window,512,axis=1,workers=1))
    mel=lambda hz:1127.*np.log1p(hz/700.)
    edges=np.linspace(mel(125.),mel(7500.),66)
    bins=mel(np.linspace(0,8000,257))[:,None]
    weights=np.maximum(0,np.minimum((bins-edges[:-2])/(edges[1:-1]-edges[:-2]),
                                  (edges[2:]-bins)/(edges[2:]-edges[1:-1])))
    weights[0]=0
    return np.log(spectrum@weights+.001)

def validate(out):
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    engine=ms.Engine(); session=engine.session('gate'); labels=engine.labels('gate')
    rng=np.random.RandomState(51773)
    signals={'silence':np.zeros(48000,np.float32), 'white_noise':rng.uniform(-1,1,48000).astype(np.float32),
        'sine':np.sin(2*np.pi*440*np.arange(48000)/16000).astype(np.float32),
        'impulse':np.eye(1,48000,17,dtype=np.float32).ravel(),'dc':np.full(48000,.1,np.float32)}
    expectations={'silence':'Silence','white_noise':'White noise','sine':'Sine wave'}
    report={'scope':'Independent DSP parameter/numerical check + upstream synthetic top10 checks. No TensorFlow score parity or real-world accuracy claim.',
        'thresholds':{'mel_max_abs':.01,'mel_rmse':.001},'cases':[],
        'sources':['https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/features.py',
            'https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/yamnet_test.py',
            'https://github.com/airockchip/rknn_model_zoo/blob/main/examples/yamnet/python/export_onnx.py'],
        'model':engine.manifest['models']['gate'],'validator_code':ms.fingerprint(Path(__file__))}
    fixtures={}
    for name,y in signals.items():
        outputs=dict(zip([value.name for value in session.get_outputs()],session.run(None,{'new_input':y[None,:]})))
        delta=np.abs(outputs['log_mel_spectrogram']-reference_mel(y))
        mean=outputs['scores'].mean(0); top=[labels[i] for i in np.argsort(-mean)[:10]]
        row={'name':name,'max_abs':float(delta.max()),'mean_abs':float(delta.mean()),'rmse':float(np.sqrt((delta**2).mean())),
            'top10':top,'expected_in_top10':expectations.get(name),'synthetic_label_pass':name not in expectations or expectations[name] in top}
        row['passed']=row['max_abs']<=.01 and row['rmse']<=.001 and row['synthetic_label_pass']
        report['cases'].append(row)
        fixtures[name+'_wave']=y; fixtures[name+'_scores']=outputs['scores']
    np.savez_compressed(out/'gate_fixture.npz',**fixtures)
    report['fixture']=ms.fingerprint(out/'gate_fixture.npz')
    report['passed']=all(row['passed'] for row in report['cases'])
    ms.write_json(out/'GATE_VALIDATION.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return report['passed']

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('-o','--out',type=Path,required=True)
    args=parser.parse_args(); raise SystemExit(0 if validate(args.out) else 1)
