"""Portable Store collector contracts, with no Apple execution or genuine pixels claimed."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
import capture_vision_store_checkpoint as capture
import vision_store_evidence as evidence
from vision_case_contract import select_case,case_identity

JPEG=b'\xff\xd8\xff\xc0'+struct.pack('>HBHHB',17,8,2160,3840,3)+bytes([1,17,0,2,17,0,3,17,0])+b'\xff\xd9'
DEVICE='11111111-1111-4111-8111-111111111111';SOURCE='a'*40

def completed(code=0):return {'state':'completed','cleanup_confirmed':True,'exit':code}

class OriginalCapture(unittest.TestCase):
 def exercise(self,mode):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp).resolve();row={'id':DEVICE};calls=[]
   def run(args,seconds,**kwargs):
    calls.append((args,seconds));(root/capture.ORIGINAL).write_bytes(JPEG if mode!='bad-image' else b'incomplete')
    if mode=='timeout':return 124,'timeout',dict(completed(124),state='timed_out')
    if mode=='unknown':return 0,'',dict(completed(),cleanup_confirmed=False)
    if mode=='nonzero':return 1,'failed',completed(1)
    return 0,'native screenshot completed',completed()
   with patch.object(capture,'blocked',return_value=False),patch.object(capture,'mark_unconfirmed') as latch:
    if mode=='success':capture.capture_original(root,DEVICE,row,run)
    else:
     with self.assertRaises(ValueError):capture.capture_original(root,DEVICE,row,run)
    self.assertTrue((root/capture.ORIGINAL).exists());self.assertEqual(len(calls),1)
    self.assertEqual(calls[0][1],20);self.assertIn('--type=jpeg',calls[0][0]);self.assertNotIn('-Z',calls[0][0])
    self.assertEqual(latch.called,mode in ('timeout','unknown'))
    with self.assertRaises(ValueError):capture.capture_original(root,DEVICE,row,run)
    self.assertEqual(len(calls),1)
    return row
 def test_original_success_and_no_retry(self):
  row=self.exercise('success');self.assertTrue(row['success']);self.assertEqual(row['dimensions'],[3840,2160]);self.assertEqual(row['sha256'],hashlib.sha256(JPEG).hexdigest())
 def test_original_preserved_on_failure_timeout_uncertainty_and_invalid_pixels(self):
  for mode in ['timeout','unknown','nonzero','bad-image']:
   with self.subTest(mode=mode):self.exercise(mode)
 def test_dimensions_require_complete_three_channel_jpeg(self):
  self.assertEqual(capture.jpeg_dimensions(JPEG),[3840,2160])
  for data in [b'',JPEG[:-1],JPEG[:10],b'PNG',JPEG.replace(bytes([3,1,17]),bytes([4,1,17]))]:
   with self.subTest(data=data[:10]),self.assertRaises(ValueError):capture.jpeg_dimensions(data)
 def test_lookup_timeout_unknown_and_interrupt_latch_before_followup(self):
  for mode in ['timeout','unknown','exception','completed-nonzero','success']:
   with tempfile.TemporaryDirectory() as temp:
    root=Path(temp).resolve();calls=[]
    def run(args,seconds,**kwargs):
     calls.append(args)
     if mode=='exception':raise RuntimeError('spawn interrupted')
     code=124 if mode=='timeout' else 1 if mode=='completed-nonzero' else 0
     op=dict(completed(code),state='timed_out' if mode=='timeout' else 'completed')
     if mode=='unknown':op.pop('cleanup_confirmed')
     return code,'exact lookup output',op
    with patch.object(capture,'blocked',return_value=False),patch.object(capture,'mark_unconfirmed') as latch:
     if mode=='success':self.assertEqual(capture.lookup_runner(root,DEVICE,capture.RUNNER,run),'exact lookup output')
     else:
      with self.assertRaises((ValueError,RuntimeError)):capture.lookup_runner(root,DEVICE,capture.RUNNER,run)
     self.assertEqual(latch.called,mode in ['timeout','unknown','exception'])
     saved=json.loads((root/'store-runner-lookup.json').read_text())
     if mode!='exception':self.assertEqual(saved['output'],'exact lookup output')
     with self.assertRaises(ValueError):capture.lookup_runner(root,DEVICE,capture.RUNNER,run)
     self.assertEqual(len(calls),1)
 def test_lookup_uncertainty_latches_before_failed_receipt_write(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp).resolve();writes=[]
   def write(path,row):
    writes.append(dict(row))
    if len(writes)>1:raise OSError('receipt unavailable')
   def run(*args,**kwargs):return 124,'timed out',dict(completed(124),state='timed_out')
   with patch.object(capture,'blocked',return_value=False),patch.object(capture,'write_json',side_effect=write),patch.object(capture,'mark_unconfirmed') as latch:
    with self.assertRaises(OSError):capture.lookup_runner(root,DEVICE,capture.RUNNER,run)
    latch.assert_called_once();self.assertEqual(latch.call_args.args[0]['state'],'store_runner_lookup_uncertain')
 def test_blocked_or_existing_attempt_prevents_new_command(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp).resolve()
   with patch.object(capture,'blocked',return_value=True),patch.object(capture,'execute') as run:
    with self.assertRaises(ValueError):capture.capture_original(root,DEVICE,{'id':DEVICE},run)
    run.assert_not_called()
   (root/'store-capture-attempt.json').write_text('{}')
   with patch.object(capture,'blocked',return_value=False),patch.object(capture,'execute') as run:
    with self.assertRaises(FileExistsError):capture.capture_original(root,DEVICE,{'id':DEVICE},run)
    run.assert_not_called()

class EvidenceRetention(unittest.TestCase):
 def setup_files(self,root):
  runtime=root/'build/vision-runtime';runtime.mkdir(parents=True)
  case=select_case('visionos_store');expected=case_identity(case,SOURCE,DEVICE)
  binding=dict(expected,success=True,exports=False,lease=DEVICE,runner='100mango.QRCatcherVisionUITests.xctrunner',pid=42)
  row=dict(binding,id=DEVICE,checkpoint=capture.NAME,file=capture.ORIGINAL,pixels_retained=True,screenshot_exit=0,screenshot_operation=completed(),bytes=len(JPEG),sha256=hashlib.sha256(JPEG).hexdigest())
  report=dict(expected,cases=[dict(expected,state='finished',exit=0,operation=completed())],capture_cleanup_confirmed=True,capture_process_exit=0)
  for name,data in [('runner-bindings.json',[binding]),('checkpoint-captures.json',[row]),('ui-cases.json',report)]:
   (runtime/name).write_text(json.dumps(data))
  (runtime/capture.ORIGINAL).write_bytes(JPEG)
  return runtime,expected,row
 def environment(self):return patch.dict(os.environ,{'GITHUB_SHA':SOURCE,'GITHUB_RUN_ID':'123','EVIDENCE_SCOPE':'visionos_store','VISION_SIMULATOR_ID':DEVICE},clear=True)
 def test_valid_checkpoint_revalidates_original_hash_dimensions_and_lease(self):
  with tempfile.TemporaryDirectory() as temp:
   runtime,expected,row=self.setup_files(Path(temp).resolve());self.assertEqual(evidence.validate_capture(runtime,expected),row)
   (runtime/capture.ORIGINAL).write_bytes(JPEG+b'changed')
   with self.assertRaises(ValueError):evidence.validate_capture(runtime,expected)
 def test_failed_ui_still_retains_untouched_original_and_logs(self):
  with tempfile.TemporaryDirectory() as temp,self.environment():
   root=Path(temp).resolve();runtime,_,_=self.setup_files(root);(root/'vision-ui-test.log').write_text('original failed test\n')
   report=evidence.collect(root,'visionos_store',allow_encode=False,failure_reason='Original UI failed')
   self.assertFalse(report['qualified']);self.assertTrue(report['capture_qualified']);self.assertFalse(report['store_upload_qualified']);self.assertTrue(report['native_original_preserved'])
   self.assertEqual((root/'build/vision-store-evidence'/capture.ORIGINAL).read_bytes(),JPEG)
   self.assertIn('original failed test',(root/'build/vision-store-evidence/vision-ui-test.log').read_text())
 def test_encoding_failure_does_not_drop_original(self):
  with tempfile.TemporaryDirectory() as temp,self.environment():
   root=Path(temp).resolve();self.setup_files(root)
   with patch('vision_store_image.retain_store_image',side_effect=ValueError('encoding failed')):
    report=evidence.collect(root,'visionos_store')
   self.assertFalse(report['qualified']);self.assertEqual((root/'build/vision-store-evidence'/capture.ORIGINAL).read_bytes(),JPEG)
 def test_success_has_separate_pixel_review_upload_boundary(self):
  with tempfile.TemporaryDirectory() as temp,self.environment():
   root=Path(temp).resolve();self.setup_files(root)
   def encode(original,destination):destination.write_bytes(original.read_bytes());return {'encoding':'original','dimensions':[3840,2160]}
   with patch('vision_store_image.retain_store_image',side_effect=encode):report=evidence.collect(root,'visionos_store')
   self.assertTrue(report['qualified']);self.assertTrue(report['pixel_review_pending']);self.assertFalse(report['store_upload_qualified'])
 def test_cross_scope_wrong_lease_and_duplicate_frames_reject(self):
  for mode in ['scope','lease','duplicate']:
   with tempfile.TemporaryDirectory() as temp:
    runtime,expected,row=self.setup_files(Path(temp).resolve())
    if mode=='scope':row['scope']='visionos_photos'
    if mode=='lease':row['lease']='22222222-2222-4222-8222-222222222222'
    (runtime/'checkpoint-captures.json').write_text(json.dumps([row,row] if mode=='duplicate' else [row]))
    with self.assertRaises(ValueError):evidence.validate_capture(runtime,expected)
 def test_artifact_rejects_links_oversized_unknown_files(self):
  for mode in ['link','hardlink','oversized','unexpected']:
   with tempfile.TemporaryDirectory() as temp:
    root=Path(temp).resolve();folder=root/'artifact';folder.mkdir();outside=root/'source.jpg';outside.write_bytes(JPEG);path=folder/'frame.jpg'
    if mode=='link':path.symlink_to(outside)
    elif mode=='hardlink':path.hardlink_to(outside)
    elif mode=='oversized':path.write_bytes(b'x'*450001)
    else:(folder/'binary.dmg').write_bytes(b'x')
    with self.assertRaises(ValueError):evidence.inspect(folder)

if __name__=='__main__':unittest.main()
