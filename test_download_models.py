"""Downloader failure/recovery contracts with controlled transport; no Internet."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import download_models as dm


class Response(io.BytesIO):
    status=200
    def __init__(self,data,url='https://models.invalid/model',length=True):
        super().__init__(data);self.url=url
        self.headers={'Content-Length':str(len(data))} if length else {}
    def geturl(self):return self.url


class DownloaderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.bundle=self.root/'bundled';self.bundle.mkdir()
        self.out=self.root/'store';self.out.mkdir()
        self.data=b'controlled model bytes; not a real neural model'
        self.meta=b'{"classes":["control"]}'
        rec=lambda name,data:{'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        self.item={'weights':rec('control.onnx',self.data),'metadata':rec('control.json',self.meta),
                   'license':'Apache-2.0','official_url':'https://models.invalid/control.onnx'}
        (self.bundle/'control.json').write_bytes(self.meta)
        self.manifest={'models':{'gate':self.item}}
    def acquire(self,opener=None,repair=False):
        return dm.acquire(self.manifest,('gate',),self.out,self.bundle,repair,opener=opener,output=lambda _:None)
    def leftovers(self):return list(self.out.glob('.*.part'))
    def test_gate_selection_does_not_require_five_music_models(self):
        self.assertEqual(dm.selected(self.manifest,'gate'),('gate',))
    def test_manifest_path_traversal_rejected(self):
        for name in ('../bad.onnx','sub/bad.onnx','sub\\bad.onnx','C:bad.onnx'):
            with self.assertRaises(ValueError):dm.target_path(self.out,{'name':name})
        self.assertFalse((self.root/'bad.onnx').exists())
    def test_plain_http_source_rejected(self):
        self.item['official_url']='http://models.invalid/control.onnx'
        with self.assertRaises(ValueError):dm.selected(self.manifest,'gate')
    def test_verified_acquisition_includes_pinned_metadata(self):
        self.assertEqual(self.acquire(lambda *a,**k:Response(self.data)),{'gate':'downloaded_verified'})
        self.assertEqual((self.out/'control.onnx').read_bytes(),self.data)
        self.assertEqual((self.out/'control.json').read_bytes(),self.meta)
        self.assertFalse(self.leftovers())
    def test_existing_valid_weight_makes_no_network_request(self):
        (self.out/'control.onnx').write_bytes(self.data)
        def no_network(*a,**k):raise AssertionError('must skip valid file')
        self.assertEqual(self.acquire(no_network),{'gate':'already_verified'})
    def test_same_size_wrong_sha_rejected_and_temp_removed(self):
        with self.assertRaisesRegex(ValueError,'SHA256'):
            self.acquire(lambda *a,**k:Response(b'x'*len(self.data)))
        self.assertFalse((self.out/'control.onnx').exists());self.assertFalse(self.leftovers())
    def test_truncated_stream_rejected(self):
        with self.assertRaises(ValueError):self.acquire(lambda *a,**k:Response(self.data[:-1],length=False))
        self.assertFalse((self.out/'control.onnx').exists());self.assertFalse(self.leftovers())
    def test_oversized_stream_rejected_without_unbounded_write(self):
        with self.assertRaisesRegex(ValueError,'exceeds'):
            self.acquire(lambda *a,**k:Response(self.data+b'extra',length=False))
        self.assertFalse(self.leftovers())
    def test_http_content_length_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,'HTTP size'):
            self.acquire(lambda *a,**k:Response(b'short'))
        self.assertFalse(self.leftovers())
    def test_https_redirect_downgrade_rejected(self):
        with self.assertRaisesRegex(ValueError,'downgrade'):
            self.acquire(lambda *a,**k:Response(self.data,url='http://models.invalid/x'))
        self.assertFalse(self.leftovers())
    def test_interrupted_read_cleans_only_own_partial(self):
        class Broken(Response):
            def read(self,n=-1):raise ConnectionResetError('controlled disconnect')
        (self.out/'unrelated.part').write_bytes(b'keep')
        with self.assertRaises(ConnectionResetError):self.acquire(lambda *a,**k:Broken(self.data))
        self.assertFalse(self.leftovers());self.assertEqual((self.out/'unrelated.part').read_bytes(),b'keep')
    def test_http_404_leaves_no_weight_or_partial(self):
        def fail(*a,**k):raise urllib.error.HTTPError('https://models.invalid/x',404,'not found',{},None)
        with self.assertRaises(urllib.error.HTTPError):self.acquire(fail)
        self.assertFalse((self.out/'control.onnx').exists());self.assertFalse(self.leftovers())
    def test_existing_corrupt_weight_not_implicitly_overwritten(self):
        dest=self.out/'control.onnx';dest.write_bytes(b'x'*len(self.data))
        with self.assertRaisesRegex(ValueError,'left untouched'):
            self.acquire(lambda *a,**k:Response(self.data))
        self.assertEqual(dest.read_bytes(),b'x'*len(self.data))
    def test_failed_explicit_repair_preserves_previous_file(self):
        dest=self.out/'control.onnx';dest.write_bytes(b'previous bytes')
        with self.assertRaises(ValueError):self.acquire(lambda *a,**k:Response(b'x'*len(self.data)),repair=True)
        self.assertEqual(dest.read_bytes(),b'previous bytes');self.assertFalse(self.leftovers())
    def test_successful_explicit_repair_replaces_only_after_validation(self):
        dest=self.out/'control.onnx';dest.write_bytes(b'previous bytes')
        self.acquire(lambda *a,**k:Response(self.data),repair=True)
        self.assertEqual(dest.read_bytes(),self.data)
    def test_bad_bundled_metadata_fails_before_transport(self):
        (self.bundle/'control.json').write_bytes(b'bad')
        def no_network(*a,**k):raise AssertionError('must not request')
        with self.assertRaisesRegex(ValueError,'Bundled metadata'):self.acquire(no_network)
        self.assertEqual(list(self.out.iterdir()),[])
    def test_cli_refusal_does_not_create_destination(self):
        dest=self.root/'absent'
        with patch('builtins.input',return_value='no'),patch.object(dm,'acquire',side_effect=AssertionError('must not acquire')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(dm.main(['--only','gate','--models-dir',str(dest)]),2)
        self.assertFalse(dest.exists())
    def test_cli_eof_does_not_assume_confirmation(self):
        with patch('builtins.input',side_effect=EOFError),patch.object(dm,'acquire',side_effect=AssertionError('must not acquire')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(dm.main(['--only','gate','--models-dir',str(self.out)]),2)
    def test_check_is_read_only_and_rejects_corruption(self):
        dest=self.out/'control.onnx';dest.write_bytes(b'x'*len(self.data))
        result=dm.check_store(self.manifest,('gate',),self.out)
        self.assertFalse(result['gate']['weights']);self.assertEqual(dest.read_bytes(),b'x'*len(self.data))
    def test_license_notice_exposes_conflict(self):
        manifest={'models':{'effnet':self.item}}
        output=[];dm.show_licenses(manifest,('effnet',),output.append)
        self.assertTrue(any('UNRESOLVED' in text and 'NoDerivatives' in text for text in output))


if __name__=='__main__':unittest.main()
