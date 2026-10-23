"""Numerical fixture and substantive semantic output/cache/decoder contracts."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import soundfile as sf
import music_semantics as ms
import semantic_frontend as front

class SemanticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine=ms.Engine()
        cls.labels={k:cls.engine.labels(k) for k in ['gate','effnet','moodtheme','voice','musicnn','deam']}
    def arrays(self):
        edges=np.linspace(0,10,9)
        rows={'gate_scores':np.zeros((8,521),np.float32),'gate_cells':np.stack([edges[:-1],edges[1:]],axis=1),
              'gate_support':np.stack([edges[:-1],edges[1:]],axis=1),'gate_reliable':np.ones(8,bool)}
        rows['gate_scores'][:,132]=1
        for group,size in [('effnet',128),('musicnn',187)]:
            starts=np.array([0,62,124,186,248,310,372,434],np.int64)
            cells,support=ms.cells(starts,size,10.)
            rows[group+'_cells']=cells; rows[group+'_support']=support
            rows[group+'_starts']=starts; rows[group+'_active']=np.ones(len(starts),bool)
            rows[group+'_energy_active']=np.ones(len(starts),bool)
        for name,width in [('effnet',400),('musicnn',50),('moodtheme',56),('voice',2),('deam',2)]:
            rows[name+'_scores']=np.zeros((8,width),np.float32)
        rows['effnet_scores'][:,0]=.8
        rows['moodtheme_scores'][:,self.labels['moodtheme'].index('sad')]=.7
        rows['voice_scores'][:,0]=.8; rows['voice_scores'][:,1]=.2
        rows['deam_scores'][:]=[3,4]
        return rows
    def test_official_frontend_fixture(self):
        validation=json.loads((ms.ROOT/'FRONTEND_VALIDATION.json').read_text())
        fixture=ms.ROOT/'tests/fixtures/frontend_fixture.npz'
        self.assertEqual(ms.sha(fixture),validation['fixture_sha256'])
        with np.load(fixture,allow_pickle=False) as data:
            np.testing.assert_allclose(front.frame_features(data['frames']),data['expected'],rtol=0,atol=.0005)
    def test_tail_frame_and_silence_preserve_time(self):
        for n in [1,255,256,257,512,16001]:
            frames=front.audio_frames(np.zeros(n,np.float32))
            self.assertEqual(len(frames),int(np.ceil(n/256))+1)
            self.assertFalse(front.frame_features(frames).any())
    def test_patch_end_and_cell_cover_exact_duration(self):
        for n in [188,750,10001]:
            starts=front.patches(np.zeros((n,96)),187)
            self.assertEqual(starts[-1]+187,n)
            cells,_=ms.cells(starts,187,(n-1)*.016)
            self.assertAlmostEqual(np.diff(cells,axis=1).sum(),(n-1)*.016)
            self.assertTrue(np.all(cells[:-1,1]==cells[1:,0]))
    def test_decoder_wav_flac_and_resampling(self):
        import librosa
        with tempfile.TemporaryDirectory() as tmp:
            for sr in [8000,16000,22050,44100,48000]:
                x=np.sin(np.arange(sr)*2*np.pi*440/sr).astype(np.float32)*.2
                stereo=np.stack([x,x*.3],axis=1)
                p=Path(tmp)/f'{sr}.wav'; sf.write(p,stereo,sr,subtype='FLOAT')
                actual,info=ms.decode(p)
                reference,_=librosa.load(p,sr=16000,mono=True,res_type='soxr_hq')
                self.assertLessEqual(abs(len(actual)-len(reference)),1)
                np.testing.assert_allclose(actual[:min(len(actual),len(reference))],reference[:len(actual)],atol=2e-7,rtol=0)
                self.assertEqual(info['channels'],2)
            p=Path(tmp)/'flac.flac'; sf.write(p,x,48000,subtype='PCM_24')
            y,_=ms.decode(p); self.assertEqual(len(y),16000)
    def test_ffmpeg_fallback_uses_same_channel_mean(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'test.wav'
            t=np.arange(16000,dtype=np.float32)/16000
            sf.write(p,np.stack([.2*np.sin(2*np.pi*440*t),.1*np.cos(2*np.pi*1000*t)],axis=1),16000,subtype='FLOAT')
            expected,_=ms.decode(p)
            with patch.object(sf,'info',side_effect=RuntimeError('force local ffmpeg')):
                actual,info=ms.decode(p)
            np.testing.assert_allclose(actual,expected,atol=2e-7,rtol=0)
            self.assertEqual(info['decoder'],'local_ffmpeg_pcm_f32le')
    def test_missing_models_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.wav'; sf.write(p,np.ones(64000)*.1,16000)
            doc=ms.analyze(p,Path(tmp)/'result',models_dir=Path(tmp)/'absent')
            self.assertEqual(doc['status'],'unavailable')
            self.assertIn('未下载',doc['reason'])
    def test_same_size_corrupt_weight_rejected_by_hash(self):
        record=self.engine.manifest['models']['effnet']['weights']
        with tempfile.TemporaryDirectory() as tmp:
            bad=Path(tmp)/record['name']
            with bad.open('wb') as stream: stream.truncate(record['bytes'])
            self.assertEqual(bad.stat().st_size,record['bytes'])
            with self.assertRaisesRegex(ValueError,record['name'].replace('.','\\.')):
                ms.verify_models(tmp)
    def test_silence_and_short_skip_all_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i,y in enumerate([np.zeros(64000,np.float32),np.ones(32000,np.float32)*.1]):
                p=Path(tmp)/f'{i}.wav'; sf.write(p,y,16000)
                with patch.object(ms,'infer_audio',side_effect=AssertionError('must skip')):
                    doc=ms.analyze(p,Path(tmp)/str(i),engine=self.engine)
                self.assertEqual(doc['status'],'insufficient_evidence')
                self.assertNotIn('styles',doc['global'])
    def test_cache_roundtrip_and_corruption(self):
        arrays=self.arrays(); ms.validate_arrays(arrays,10.)
        with tempfile.TemporaryDirectory() as tmp:
            ms.save_cache(tmp,'test',arrays)
            cached=ms.read_cache(tmp,'test',10.)
            self.assertIsNotNone(cached)
            for key in arrays: np.testing.assert_array_equal(arrays[key],cached[key])
            (Path(tmp)/'test.npz').write_bytes(b'corrupted')
            self.assertIsNone(ms.read_cache(tmp,'test',10.))
    def test_invalid_cache_nan_wrong_shape_and_time_rejected(self):
        for kind in ['nan','width','gap','start']:
            arrays=self.arrays()
            if kind=='nan': arrays['voice_scores'][0,0]=np.nan
            if kind=='width': arrays['deam_scores']=np.zeros((8,3),np.float32)
            if kind=='gap': arrays['effnet_cells'][1,0]+=.1
            if kind=='start': arrays['effnet_starts'][0]=1
            with self.assertRaises(ValueError): ms.validate_arrays(arrays,10.)
    def test_cache_key_changes_for_source_weights_code_frontend(self):
        original=ms.cache_key('source','weights','code')
        for args in [('other','weights','code'),('source','other','code'),('source','weights','other')]:
            self.assertNotEqual(original,ms.cache_key(*args))
        with patch.dict(ms.SETTINGS,frontend='different'):
            self.assertNotEqual(original,ms.cache_key('source','weights','code'))
    def test_aggregation_does_not_double_count_overlapping_windows(self):
        a=self.arrays(); scores,seconds,ids=ms.weighted(a,'effnet',0,10)
        self.assertAlmostEqual(seconds,10)
        self.assertAlmostEqual(scores[0],.8,places=6)
        self.assertEqual(len(ids),8)
    def test_mood_theme_separation_and_parent_max(self):
        a=self.arrays(); a['moodtheme_scores'][:,self.labels['moodtheme'].index('film')]=.99
        d=ms.describe(a,self.labels,0,10)
        self.assertEqual(d['mood']['candidates'][0]['label'],'sad')
        self.assertEqual(d['themes']['candidates'][0]['label'],'film')
        self.assertEqual(d['styles']['parent_genres'][0]['aggregation'],'max_child_score_not_probability')
    def test_ambiguity_and_disagreement_not_erased(self):
        a=self.arrays(); a['effnet_scores'][:,1]=.79; a['voice_scores'][:]=.5; a['deam_scores'][:,0]=7
        d=ms.describe(a,self.labels,0,10)
        self.assertEqual(d['status'],'ambiguous')
        self.assertEqual(d['voice_type']['status'],'ambiguous')
        self.assertIn('negative_tag_vs_high_valence',d['disagreements'])
    def test_axes_order_and_out_of_range_not_clipped(self):
        a=self.arrays(); a['deam_scores'][:]=[10.,-2.]
        d=ms.describe(a,self.labels,0,10)['affect']
        self.assertEqual((d['valence'],d['arousal']),(10.,-2.))
        self.assertTrue(d['out_of_reference_range'])
        self.assertEqual(self.labels['deam'],['valence','arousal'])
    def test_short_window_and_inactive_support_no_claims(self):
        a=self.arrays()
        self.assertNotIn('styles',ms.describe(a,self.labels,9,10))
        a['effnet_active'][:]=False
        d=ms.describe(a,self.labels,0,10)
        self.assertEqual(d['styles']['level'],'coarse')
        self.assertNotIn('affect',d)
    def test_query_rejects_modified_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'scores.npz'; np.savez(path,**self.arrays())
            doc={'schema_version':ms.SCHEMA,'duration':10,'source':{},'labels':self.labels,'raw_evidence':ms.fingerprint(path),'warnings':[]}
            self.assertEqual(ms.query(doc,tmp,0,3)['windows'],[])
            path.write_bytes(b'modified')
            with self.assertRaises(ValueError): ms.query(doc,tmp,0,3)
    def test_input_invalid_nonfinite_rejected(self):
        for frames in [np.full((2,512),np.nan),np.zeros((2,513))]:
            with self.assertRaises(ValueError): front.frame_features(frames)
    def test_query_rounding_tolerance_only_one_canonical_sample(self):
        doc={'schema_version':ms.SCHEMA,'duration':10.,'source':{},'warnings':[]}
        ms.query(doc,ms.ROOT,0.,10.+1/22050)
        with self.assertRaises(ValueError): ms.query(doc,ms.ROOT,0.,10.+2/16000)
    def test_compact_omits_global_patch_lists_without_mutation(self):
        doc={'global':ms.describe(self.arrays(),self.labels,0,10)}
        compact=ms.compact(doc)
        self.assertNotIn('support_patch_ids',compact['global'])
        self.assertEqual(compact['global']['support_patch_ids_count'],8)
        self.assertEqual(len(doc['global']['support_patch_ids']),8)
    def test_session_cpu_and_bounded_thread_configuration(self):
        for name,threads in [('voice',1),('effnet',2)]:
            session=self.engine.session(name)
            self.assertEqual(session.get_providers(),['CPUExecutionProvider'])
            self.assertEqual(session.get_session_options().intra_op_num_threads,threads)
            self.assertEqual(session.get_session_options().get_session_config_entry('session.intra_op.allow_spinning'),'0')
    def test_models_labels_pinned_in_manifest(self):
        self.assertEqual(len(self.labels['effnet']),400)
        self.assertEqual(len(self.labels['moodtheme']),56)
        self.assertEqual(self.labels['voice'],['instrumental','voice'])
        self.assertEqual(self.engine.manifest['total_weight_bytes'],40640925)

if __name__=='__main__': unittest.main(verbosity=2)
