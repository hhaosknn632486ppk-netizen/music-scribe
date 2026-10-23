"""Safety-of-conclusion contracts, including mixed recordings and scoped queries."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
import music_gate as gate
import music_semantics as ms
import test_semantics as semantic_tests

class GateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine=ms.Engine(); cls.labels={k:cls.engine.labels(k) for k in ['gate','effnet','musicnn','moodtheme','voice','deam']}
        cls.helper=semantic_tests.SemanticTests(); cls.helper.labels=cls.labels
    def arrays(self): return self.helper.arrays()
    def test_speech_blocks_all_music_descriptions(self):
        a=self.arrays(); a['gate_scores'][:]=0; a['gate_scores'][:,0]=.99
        d=ms.describe(a,self.labels,0,10)
        self.assertEqual(d['status'],'not_music')
        for field in ['styles','mood','themes','voice_type','affect']: self.assertNotIn(field,d)
    def test_unknown_low_support_does_not_force_a_label(self):
        a=self.arrays(); a['gate_scores'][:]=.01
        d=ms.describe(a,self.labels,0,10)
        self.assertEqual(d['status'],'uncertain_input'); self.assertNotIn('styles',d)
    def test_single_short_music_peak_cannot_unlock_classifier(self):
        n=12; edges=np.arange(n+1)*.48
        a={'gate_scores':np.zeros((n,521),np.float32),'gate_cells':np.stack([edges[:-1],edges[1:]],1),
           'gate_support':np.stack([edges[:-1],edges[1:]],1),'gate_reliable':np.ones(n,bool)}
        a['gate_scores'][5,132]=.99
        self.assertFalse(gate.music_mask(a).any())
        self.assertFalse(gate.describe(a,self.labels['gate'],0,edges[-1])['semantics_allowed'])
    def test_speech_and_music_together_are_allowed_mixed(self):
        a=self.arrays(); a['gate_scores'][:,0]=.9
        d=ms.describe(a,self.labels,0,10)
        self.assertEqual(d['music_presence']['status'],'mixed'); self.assertIn('styles',d)
    def test_context_crossing_speech_is_excluded(self):
        a=self.arrays(); a['gate_scores'][4:,132]=0; a['gate_scores'][4:,0]=1
        contexts=np.array([[0,3],[4,7],[6,9]],float)
        np.testing.assert_array_equal(gate.context_mask(a,contexts),[True,False,False])
        self.assertAlmostEqual(gate.overlap_weights(a,np.array([[0,10.]]))[0],5.)
    def test_non_music_files_only_load_gate_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'noise.wav'; sf.write(path,np.random.default_rng(99).normal(0,.1,16000*6),16000,subtype='PCM_16')
            engine=ms.Engine()
            with patch.object(ms,'infer_audio',side_effect=AssertionError('music classifiers must not run')):
                doc=ms.analyze(path,Path(tmp)/'result',engine=engine)
            self.assertFalse(doc['classification_ran']); self.assertEqual(set(engine.sessions),{'gate'})
            self.assertNotIn('styles',doc['global'])
    def test_low_fine_score_falls_back_to_parent_without_leaf_label(self):
        a=self.arrays(); a['effnet_scores'][:,0]=.20
        d=ms.describe(a,self.labels,0,10)
        self.assertEqual(d['styles']['level'],'coarse'); self.assertEqual(d['styles']['candidates'][0]['label'],'Blues')
        self.assertNotIn('---',json.dumps(d['styles'],ensure_ascii=False))
    def test_conflicting_parent_evidence_prevents_fine_claim(self):
        a=self.arrays(); a['gate_scores'][:,self.labels['gate'].index('Rock music')]=.9
        d=ms.describe(a,self.labels,0,10)
        self.assertEqual(d['styles']['level'],'coarse'); self.assertEqual(d['styles']['candidates'][0]['label'],'Rock')
    def test_unstable_leaf_falls_back_even_with_large_average(self):
        a=self.arrays(); a['effnet_scores'][:,0]=.7; a['effnet_scores'][:4,1]=.9
        d=ms.describe(a,self.labels,0,10)
        self.assertEqual(d['styles']['level'],'coarse')
    def test_supported_consistent_leaf_can_remain_fine(self):
        d=ms.describe(self.arrays(),self.labels,0,10)
        self.assertEqual(d['styles']['level'],'fine')
    def test_purpose_category_cannot_be_promoted_to_genre(self):
        a=self.arrays(); a['effnet_scores'][:]=0
        a['effnet_scores'][:,self.labels['effnet'].index('Stage & Screen---Soundtrack')]=.95
        d=ms.describe(a,self.labels,0,10)
        self.assertEqual(d['styles']['level'],'coarse')
        self.assertNotIn('Soundtrack',ms.summary_text(d))
    def test_generic_fallback_is_not_an_invented_genre(self):
        a=self.arrays(); a['effnet_scores'][:]=.001
        d=ms.describe(a,self.labels,0,10)
        self.assertEqual(d['styles']['candidates'][0]['kind'],'content_type_not_genre')
    def test_gate_cache_corruption_and_missing_gate_rejected(self):
        a=self.arrays(); del a['gate_scores']
        with self.assertRaises(KeyError): ms.validate_arrays(a,10)
        a=self.arrays(); a['gate_cells'][2,0]+=.01
        with self.assertRaises(ValueError): ms.validate_arrays(a,10)
    def test_semantic_rows_outside_music_cannot_contain_hidden_scores(self):
        a=self.arrays(); a['gate_scores'][4:,132]=0
        with self.assertRaises(ValueError): ms.validate_arrays(a,10)
    def test_gate_clock_covers_tail_without_treating_padded_only_frames_as_audio(self):
        for n in [16000*3,16000*3+1,16000*7+500]:
            a=gate.infer(np.zeros(n,np.float32),self.engine)
            gate.validate(a,n/16000)
            self.assertAlmostEqual(np.diff(a['gate_cells'],axis=1).sum(),n/16000)
            self.assertLessEqual(a['gate_support'].max(),n/16000)
            self.assertFalse(gate.music_mask(a).any())
    def test_query_in_speech_does_not_leak_whole_song_style(self):
        a=self.arrays(); a['gate_scores'][4:,132]=0; a['gate_scores'][4:,0]=.99
        for group in ['effnet','musicnn']:
            a[group+'_active']=a[group+'_energy_active'] & gate.context_mask(a,a[group+'_support'])
        for name in ['effnet','moodtheme','voice','musicnn','deam']:
            group='musicnn' if name in ['musicnn','deam'] else 'effnet'
            a[name+'_scores'][~a[group+'_active']]=0
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/'scores.npz'; np.savez(raw,**a)
            doc={'schema_version':ms.SCHEMA,'duration':10.,'source':{},'raw_evidence':ms.fingerprint(raw),
                'labels':self.labels,'global':ms.describe(a,self.labels,0,10),'warnings':[],
                'windows':[dict(ms.describe(a,self.labels,0,10),id='w00000')]}
            result=ms.query(doc,tmp,6,10)
            self.assertIsNone(result['global']); self.assertEqual(result['windows'],[])
            self.assertNotIn('styles',result['decision']); self.assertTrue(result['withheld_window_contexts'])

if __name__=='__main__': unittest.main(verbosity=2)
