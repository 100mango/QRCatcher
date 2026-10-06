"""Bounded selected export with explicit command doubles; no native runtime proof."""
import ast
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import ios_original_release_route as original
import ios_original_supplement_route as route
from validate_evidence_budget import inspect

EXPORTER=ROOT/'scripts/export_ios_platform_screenshots.py'
TREE=ast.parse(EXPORTER.read_text())
NAMESPACE={'hashlib':hashlib,'json':json,'math':math,'os':os,'pathlib':__import__('pathlib'),'re':re}
exec(compile(ast.Module(body=[node for node in TREE.body if isinstance(node,ast.FunctionDef)],type_ignores=[]),'<selected exporter functions>','exec'),NAMESPACE)
identity=NAMESPACE['supplement_identity']
contract=NAMESPACE['supplement_contract']
classify=NAMESPACE['classify_supplement_result']
retain=NAMESPACE['retain_supplement_records']
strict=NAMESPACE['strict_record']
export_blocked=NAMESPACE['supplement_export_blocked']
SHA='a'*40
SOURCE_TREE='b'*40
DEVICE='11111111-2222-4333-8444-555555555555'


class SupplementExportTests(unittest.TestCase):
 @contextlib.contextmanager
 def fixture(self,scope='ipad_mini'):
  with tempfile.TemporaryDirectory(prefix='qr-selected-export-') as name:
   root=Path(name).resolve();before=Path.cwd()
   (root/'build').mkdir();(root/'scripts').mkdir()
   canonical=(ROOT/original.CANONICAL).read_text()
   workflow=route.render_workflow(canonical) if scope in route.PHONE_SCOPES else route.render_legacy_workflow(canonical)
   for path,text in ((original.CANONICAL,canonical),(original.WORKFLOW,original.render_workflow(canonical)),(route.WORKFLOW,workflow)):
    target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
   shutil.copyfile(ROOT/'scripts/evidence-allocation.json',root/'scripts/evidence-allocation.json')
   env={'GITHUB_REPOSITORY':original.REPOSITORY,'GITHUB_SHA':SHA,'GITHUB_WORKFLOW_SHA':SHA,
    'GITHUB_REF':route.REF,'GITHUB_WORKFLOW_REF':route.WORKFLOW_REF,'GITHUB_EVENT_NAME':'push',
    'IOS_FIRST_RELEASE_CANDIDATE_ONLY':'true','QRCATCHER_IOS_SUPPLEMENT_ONLY':'true',
    'RUNNER_OS':'macOS','RUNNER_ARCH':'ARM64','GITHUB_JOB':'platform','EVIDENCE_SCOPE':scope,
    'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','GITHUB_WORKSPACE':str(root),'GITHUB_ENV':str(root/'env'),
    'QRCATCHER_OWNED_PROCESS_BARRIER':str(root/'build/owned-process-cleanup.json'),
    'SIMULATOR_ID':DEVICE,'COMPACT_SIMULATOR_ID':DEVICE,'IPAD_SIMULATOR_ID':DEVICE,'MINI_SIMULATOR_ID':DEVICE}
   if scope in route.PHONE_SCOPES:env['PHONE_COMPLETION_ONLY']='true'
   with patch.dict(os.environ,env,clear=True):
    os.chdir(root)
    try:
     provenance={**route.current_identity(),'tested_tree':SOURCE_TREE,
      'source_readback_phase':'existing bounded managed Mini prepare HEAD/tree/diff' if scope=='ipad_mini' else 'bounded initial original iOS HEAD/tree/diff/status'}
     raw=(json.dumps(provenance)+'\n').encode()
     (root/original.RECEIPT).write_bytes(raw)
     os.environ[original.INITIAL_HASH_KEY]=hashlib.sha256(raw).hexdigest()
     (root/'build/ios-first-debug-package.json').write_text('{"package":"diagnostic"}')
     yield root
    finally:os.chdir(before)

 def operation(self,command,cap,exit_code=0,output_bytes=0):
  return {'command':command,'timeout_seconds':cap,'state':'completed','exit':exit_code,
   'cleanup_confirmed':True,'elapsed_seconds':1.5,'output_bytes':output_bytes}

 def mini_host_lease(self,root,status='completed'):
  import ipad_mini_setup as mini
  runner=root/'runner';runner.mkdir();started=time.monotonic()-5
  bound={'source':SHA,'workflow_sha':SHA,'run_id':'123','run_attempt':'1','scope':'ipad_mini'}
  origin=runner/'qrcatcher-mini-123-1.json'
  origin.write_text(json.dumps({'version':1,**bound,'caps':mini.IOS_FIRST_CAPS,'started_monotonic':started}))
  os.environ.update(RUNNER_TEMP=str(runner),QRCATCHER_MINI_JOB_ORIGIN=str(origin))
  command=[sys.executable,'scripts/export_ios_platform_screenshots.py'];now=time.monotonic()-0.01
  state={'version':1,**bound,'started_monotonic':started,'deadline_monotonic':started+3000,
   'phases':{'mini':{'started':started,'deadline':started+2220,'status':status,'operations':[]},
    'export':{'started':now,'deadline':now+180,'status':'pending','operations':[{'command':command,'cap':155,'status':'pending'}]}}}
  (root/'build/ipad-mini-job-state.json').write_text(json.dumps(state))
  (root/'build/ipad-mini-row-dispatched.json').write_text(json.dumps({**bound,'phase':'full_row_dispatched_once','owner_pid':12345,'command':None}))
  host={**bound,'phase':'host-export','owner_pid':os.getppid(),'command':command}
  (root/'build/ipad-mini-host-inflight.json').write_text(json.dumps(host))
  return host,state

 def produce(self,root,stem='MiniUIResults-warmup',scope='ipad_mini',failed=False):
  expected=contract(scope,stem)
  value={'result':'Failed' if failed else 'Passed','totalTestCount':expected['expected'],
   'passedTests':expected['expected']-(1 if failed else 0),'failedTests':1 if failed else 0,
   'skippedTests':0,'expectedFailures':0,'runtimeWarnings':[],
   'testFailures':[{'failureText':'retained actual failure'}] if failed else [],
   'devicesAndConfigurations':[{'device':{'deviceId':DEVICE,'platform':'iOS Simulator'}}]}
  raw=(json.dumps(value)+'\n').encode()
  native=self.operation(expected['command'],expected['cap'],65 if failed else 0,64)
  reader=self.operation(['xcrun','xcresulttool','get','test-results','summary','--path',stem+'.xcresult'],expected['summary_cap'],output_bytes=len(raw))
  records={stem+'-command.json':native,stem+'-summary-command.json':reader,stem+'-summary.json':value}
  for filename,record in records.items():
   (root/'build'/filename).write_bytes(raw if filename.endswith('-summary.json') else (json.dumps(record)+'\n').encode())
  log='ios-unit.log' if stem=='iOSUnitResults' else stem+'.log'
  (root/log).write_text('complete bounded native output\n'+json.dumps(native)+'\n')
  if scope=='ipad_mini':(root/(stem+'-summary.log')).write_text(raw.decode())
  bundle=root/(stem+'.xcresult');bundle.mkdir();(bundle/'Info.plist').write_text('owned result metadata')
  return records,raw

 def run_exporter(self,runner=None):
  with patch('subprocess.check_output',side_effect=AssertionError('Selected export cannot launch git')), patch('subprocess.run',side_effect=runner or AssertionError('Selected metadata export cannot launch a public command')):
   return runpy.run_path(str(EXPORTER),run_name='__main__')

 def test_exact_workflow_identity_rejects_source_ref_flag_and_mutation_without_process(self):
  changes={'GITHUB_SHA':'c'*40,'GITHUB_WORKFLOW_SHA':'c'*40,'GITHUB_REF':original.REF,
   'GITHUB_WORKFLOW_REF':original.WORKFLOW_REF,'QRCATCHER_IOS_SUPPLEMENT_ONLY':'false',
   'IOS_FIRST_RELEASE_CANDIDATE_ONLY':'false','GITHUB_REPOSITORY':'foreign/repository'}
  for key,value in changes.items():
   with self.subTest(key=key),self.fixture() as root,patch.dict(os.environ,{key:value}):
    with self.assertRaises(ValueError):self.run_exporter()
    self.assertFalse((root/'build/ios-platform-evidence/manifest.json').exists())
  with self.fixture() as root:
   (root/route.WORKFLOW).write_text((root/route.WORKFLOW).read_text()+'\n')
   with self.assertRaises(ValueError):self.run_exporter()

 def test_foreign_initial_source_receipt_rejects_even_with_new_digest(self):
  with self.fixture() as root:
   value=json.loads((root/original.RECEIPT).read_bytes());value['source_sha']='c'*40
   raw=json.dumps(value).encode();(root/original.RECEIPT).write_bytes(raw)
   os.environ[original.INITIAL_HASH_KEY]=hashlib.sha256(raw).hexdigest()
   with self.assertRaises(ValueError):self.run_exporter()

 def test_current_phone_fixture_and_historical_four_scope_fixture_are_explicit(self):
  for scope in route.SCOPES:
   with self.subTest(scope=scope),self.fixture(scope) as root:
    current=route.current_identity()
    self.assertEqual(current['scope'],scope)
    expected=list(route.PHONE_SCOPES) if scope in route.PHONE_SCOPES else list(route.SCOPES)
    self.assertEqual(current['selected_scopes'],expected)
    if scope in route.PHONE_SCOPES:
     self.assertEqual(os.environ['PHONE_COMPLETION_ONLY'],'true')
     with patch.dict(os.environ,{'PHONE_COMPLETION_ONLY':'false'}):
      with self.assertRaises(ValueError):identity()
    else:self.assertNotIn('PHONE_COMPLETION_ONLY',os.environ)

 def test_later_failed_seed_keeps_earlier_receipts_summaries_logs_and_no_requery(self):
  with self.fixture() as root:
   _,raw=self.produce(root)
   (root/'MiniUIResults-warmup.log').write_bytes(b'x'*130000+b'\ncomplete final native receipt\n')
   seed=self.operation(['xcrun','simctl','addmedia',DEVICE,'Tests/Fixtures/unicode.png'],210,124)
   seed['state']='timed_out';seed['cleanup_confirmed']=False
   (root/'build/MiniUIResults-seed-command.json').write_text(json.dumps(seed))
   (root/'MiniUIResults-seed.log').write_text('retained failed seed')
   (root/'build/owned-process-cleanup.json').write_text('{"blocked":true}')
   (root/'build/ipad-mini-job-state.json').write_text('{"status":"failed_or_incomplete"}')
   (root/'build/ipad-mini-owned-device.json').write_text('{"device":"'+DEVICE+'"}')
   (root/'build/ipad-mini-row-dispatched.json').write_text('{"state":"completed_selected_warmup"}')
   self.run_exporter()
   out=root/'build/ios-platform-evidence';value=json.loads((out/'manifest.json').read_text())
   self.assertEqual((out/'MiniUIResults-warmup-summary.json').read_bytes(),raw)
   self.assertEqual((out/'MiniUIResults-warmup.log').stat().st_size,64*1024)
   for name in ('MiniUIResults-warmup-command.json','MiniUIResults-warmup-summary-command.json','MiniUIResults-seed-command.json','MiniUIResults-seed.log','MiniUIResults-warmup-summary.log','ipad-mini-job-state.json','ipad-mini-owned-device.json','ipad-mini-row-dispatched.json','ios-original-release-provenance.json'):
    self.assertTrue((out/name).is_file(),name)
   selected=value['selected_evidence']
   self.assertTrue(selected['results']['MiniUIResults-warmup']['acceptance'])
   self.assertEqual(selected['results']['MiniUIResults-warmup']['attachments'],'not_exported_owned_uncertainty')
   self.assertEqual(selected['photos_seed']['exit'],124)
   self.assertFalse(selected['photos_seed']['observations_qualify_pass']);self.assertFalse(value['evidence_complete'])
   self.assertEqual(value['results']['ipad-mini']['summary_unavailable'],True)
   self.assertTrue(value['results']['ipad-mini-layout']['not_selected']);self.assertTrue(value['results']['ipad-mini-files']['not_selected'])
   self.assertEqual(selected['historical_component_reference']['run_id'],'37478641479')
   self.assertEqual(selected['historical_component_reference']['source_sha'],'dfb0dd0d8d3bd67b554950dec8aa4ee4d51031f1')
   self.assertEqual(selected['runtime_precise_safari_url'],'UNKNOWN')
   row=next(row for row in selected['files'] if row['name']=='MiniUIResults-warmup.log')
   self.assertTrue(row['truncated']);self.assertGreater(row['source_bytes'],row['bytes'])
   self.assertLessEqual(inspect(out,limit=2000000)['bytes'],2000000)

 def test_metadata_survives_optional_image_cap_saturation(self):
  with self.fixture() as root:
   _,raw=self.produce(root)
   def commands(command,**kwargs):
    self.assertEqual(command[:4],['xcrun','xcresulttool','export','attachments'])
    folder=Path(command[-1]);entries=[]
    for index in range(3):
     name='frame-'+str(index)+'.jpg';(folder/name).write_bytes(b'\xff\xd8'+b'x'*749998)
     entries.append({'exportedFileName':name,'name':'image-import-real-photos'})
    (folder/'manifest.json').write_text(json.dumps(entries))
    return subprocess.CompletedProcess(command,0,'','')
   def runner(command,**kwargs):
    if command[0]=='sips':shutil.copyfile(command[-3],command[-1]);return subprocess.CompletedProcess(command,0,'','')
    return commands(command,**kwargs)
   with self.assertRaises(SystemExit):self.run_exporter(runner)
   out=root/'build/ios-platform-evidence';value=json.loads((out/'manifest.json').read_text())
   self.assertEqual((out/'MiniUIResults-warmup-summary.json').read_bytes(),raw)
   self.assertTrue((out/'MiniUIResults-warmup-command.json').is_file());self.assertTrue(value['omitted'])
   self.assertFalse(value['evidence_complete']);self.assertFalse(value['full_original_row_qualification'])
   self.assertLessEqual(inspect(out,limit=2000000)['bytes'],2000000)

 def test_metadata_survives_attachment_command_failure(self):
  with self.fixture() as root:
   _,raw=self.produce(root)
   with self.assertRaises(subprocess.CalledProcessError):
    self.run_exporter(lambda command,**kwargs: (_ for _ in ()).throw(subprocess.CalledProcessError(1,command)))
   out=root/'build/ios-platform-evidence'
   self.assertEqual((out/'MiniUIResults-warmup-summary.json').read_bytes(),raw)
   self.assertFalse(json.loads((out/'manifest.json').read_text())['evidence_complete'])

 def test_successful_mini_export_uses_retained_summaries_inside_exact_host_lease(self):
  with self.fixture() as root:
   self.produce(root);self.produce(root,'MiniUIResults')
   self.mini_host_lease(root)
   seed=self.operation(['xcrun','simctl','addmedia',DEVICE,'Tests/Fixtures/unicode.png'],210)
   (root/'build/MiniUIResults-seed-command.json').write_text(json.dumps(seed));(root/'MiniUIResults-seed.log').write_text('complete clean seed')
   calls=[]
   def runner(command,**kwargs):
    calls.append(command);self.assertEqual(command[:4],['xcrun','xcresulttool','export','attachments'])
    Path(command[-1],'manifest.json').write_text('[]');return subprocess.CompletedProcess(command,0,'','')
   self.run_exporter(runner)
   value=json.loads((root/'build/ios-platform-evidence/manifest.json').read_text())
   self.assertEqual(len(calls),2);self.assertFalse(value['selected_evidence']['owned_process_uncertainty_observed'])
   self.assertTrue(value['evidence_complete']);self.assertFalse(value['full_original_row_qualification'])
   self.assertEqual(value['selected_evidence']['runtime_precise_safari_url'],'UNKNOWN')

 def test_later_uncertainty_blocks_conversion_and_keeps_original_receipts(self):
  with self.fixture() as root:
   _,raw=self.produce(root);calls=[]
   def runner(command,**kwargs):
    calls.append(command);folder=Path(command[-1]);(folder/'frame.jpg').write_bytes(b'\xff\xd8whole frame')
    (folder/'manifest.json').write_text('[{"exportedFileName":"frame.jpg","name":"image-import-real-photos"}]')
    (root/'build/owned-process-cleanup.json').write_text('{"blocked":true}')
    return subprocess.CompletedProcess(command,0,'','')
   with self.assertRaisesRegex(ValueError,'owned uncertainty'):self.run_exporter(runner)
   self.assertEqual(len(calls),1)
   self.assertEqual((root/'build/ios-platform-evidence/MiniUIResults-warmup-summary.json').read_bytes(),raw)

 def test_redirected_or_invalid_selected_images_reject_even_under_optimization(self):
  for variant in ('symlink','invalid_image'):
   with self.subTest(variant=variant),self.fixture() as root:
    _,raw=self.produce(root)
    def runner(command,**kwargs):
     folder=Path(command[-1]);path=folder/'frame.jpg'
     if variant=='symlink':
      outside=root/'outside.jpg';outside.write_bytes(b'\xff\xd8outside');path.symlink_to(outside)
     else:path.write_bytes(b'unknown image bytes')
     (folder/'manifest.json').write_text('[{"exportedFileName":"frame.jpg","name":"image-import-real-photos"}]')
     return subprocess.CompletedProcess(command,0,'','')
    with self.assertRaises((ValueError,AssertionError)):self.run_exporter(runner)
    self.assertEqual((root/'build/ios-platform-evidence/MiniUIResults-warmup-summary.json').read_bytes(),raw)

 def test_oversized_raw_summary_is_rejected_without_losing_native_receipt(self):
  with self.fixture() as root:
   self.produce(root);(root/'build/MiniUIResults-warmup-summary.json').write_bytes(b' '*65537)
   with self.assertRaises(SystemExit):self.run_exporter()
   out=root/'build/ios-platform-evidence';value=json.loads((out/'manifest.json').read_text())
   self.assertTrue((out/'MiniUIResults-warmup-command.json').is_file());self.assertFalse((out/'MiniUIResults-warmup-summary.json').exists())
   self.assertFalse(value['selected_evidence']['results']['MiniUIResults-warmup']['acceptance'])

 def test_semantically_invalid_summary_is_retained_without_acceptance_or_process(self):
  with self.fixture() as root:
   self.produce(root)
   path=root/'build/MiniUIResults-warmup-summary.json'
   value=json.loads(path.read_bytes());value['devicesAndConfigurations'][0]['device']['deviceId']='foreign'
   raw=json.dumps(value).encode();path.write_bytes(raw)
   reader=root/'build/MiniUIResults-warmup-summary-command.json';op=json.loads(reader.read_bytes());op['output_bytes']=len(raw);reader.write_text(json.dumps(op))
   self.run_exporter()
   out=root/'build/ios-platform-evidence';value=json.loads((out/'manifest.json').read_text())
   self.assertEqual((out/path.name).read_bytes(),raw)
   self.assertFalse(value['results']['ipad-mini-warmup']['selected_case_acceptance'])
   self.assertFalse(value['selected_evidence']['results']['MiniUIResults-warmup']['acceptance'])

 def test_closed_fixed_records_reject_duplicate_json_symlink_hardlink_empty_and_oversize(self):
  for variant in ('duplicate','symlink','hardlink','empty','oversize','array','nonfinite'):
   with self.subTest(variant=variant),self.fixture() as root:
    self.produce(root);path=root/'build/MiniUIResults-warmup-command.json'
    if variant=='duplicate':path.write_text('{"state":"completed","state":"timed_out"}')
    elif variant=='symlink':
     target=root/'outside-record.json';target.write_bytes(path.read_bytes());path.unlink();path.symlink_to(target)
    elif variant=='hardlink':os.link(path,root/'shared-record.json')
    elif variant=='empty':path.write_bytes(b'')
    elif variant=='oversize':path.write_bytes(b' '*16385)
    elif variant=='array':path.write_text('[]')
    else:path.write_text('{"elapsed_seconds":NaN}')
    with self.assertRaises(SystemExit):self.run_exporter()
    out=root/'build/ios-platform-evidence';value=json.loads((out/'manifest.json').read_text())
    self.assertFalse((out/path.name).exists());self.assertTrue(value['selected_evidence']['invalid'])
    self.assertTrue((out/'MiniUIResults-warmup-summary.json').is_file())
    self.assertFalse(value['selected_evidence']['results']['MiniUIResults-warmup']['acceptance'])

 def test_fixed_record_duplicate_output_cannot_overwrite_earlier_bytes(self):
  with self.fixture() as root:
   self.produce(root);out=root/'build/ios-platform-evidence';out.mkdir()
   previous=b'{"existing":"owned"}';(out/'MiniUIResults-warmup-command.json').write_bytes(previous)
   report,_=retain(route.current_identity(),out,2000000)
   self.assertEqual((out/'MiniUIResults-warmup-command.json').read_bytes(),previous)
   self.assertTrue(report['invalid']);self.assertFalse(report['results']['MiniUIResults-warmup']['acceptance'])

 def test_each_receipt_cannot_promote_unknown_late_unclean_foreign_or_bool_exit(self):
  with self.fixture() as root:
   records,raw=self.produce(root)
   for filename in ('MiniUIResults-warmup-command.json','MiniUIResults-warmup-summary-command.json'):
    for change in ({'state':'unknown'},{'cleanup_confirmed':False},{'exit':True},{'elapsed_seconds':math.inf},{'elapsed_seconds':999},{'command':['foreign']},{'timeout_seconds':True}):
     copy=json.loads(json.dumps(records));copy[filename].update(change)
     with self.subTest(filename=filename,change=change):self.assertFalse(classify('ipad_mini','MiniUIResults-warmup',copy,raw)['acceptance'])
   self.assertTrue(classify('ipad_mini','MiniUIResults-warmup',records,raw)['acceptance'])

 def test_finalized_failed_selected_case_stays_failed(self):
  with self.fixture() as root:
   records,raw=self.produce(root,failed=True)
   value=classify('ipad_mini','MiniUIResults-warmup',records,raw)
   self.assertTrue(value['acceptance']);self.assertEqual(value['native_outcome'],'Failed')
   self.assertFalse(value['full_original_row_qualification'])

 def test_manual_browser_image_keeps_original_bytes_without_conversion_or_page_qualification(self):
  for scope,stem,label in (('iphone_pro','PhoneUIResults','pro-max'),('iphone_se3','CompactPhoneUIResults','SE3')):
   with self.subTest(scope=scope),self.fixture(scope) as root:
    self.produce(root,stem,scope)
    native=b'\xff\xd8'+b'original native full-screen pixels'*100
    def runner(command,**kwargs):
     self.assertEqual(command[:3],['xcrun','xcresulttool','export'])
     folder=root/command[-1]
     (folder/'manual.jpg').write_bytes(native)
     (folder/'manifest.json').write_text(json.dumps([{'name':'privacy-browser-manual-review','exportedFileName':'manual.jpg'}]))
     return subprocess.CompletedProcess(command,0,'','')
    self.run_exporter(runner)
    value=json.loads((root/'build/ios-platform-evidence/manifest.json').read_text())
    image=value['screenshots'][0]
    self.assertEqual((root/'build/ios-platform-evidence'/image['name']).read_bytes(),native)
    self.assertEqual(image['result_label'],label);self.assertEqual(image['bytes'],len(native))
    self.assertTrue(image['source_bytes_preserved']);self.assertTrue(image['manual_review_required'])
    self.assertFalse(image['automatic_page_qualification']);self.assertEqual(image['runtime_precise_url'],'UNKNOWN')

 def test_fresh_vm_first_summary_mapping_keeps_later_ten_and_rejects_historical_timed_out_bytes(self):
  inventory={'iphone_pro':{'iOSUnitResults':30,'PhoneUIResults':10,'PhoneUIResults-files':10,'PhoneUIResults-imports':10},
             'iphone_se3':{'CompactPhoneUIResults':30,'CompactPhoneUIResults-files':10,'CompactPhoneUIResults-imports':10},
             'ipad_pro':{'PadUIResults-layout':30,'PadUIResults-files':10,'PadUIResults':10},
             'ipad_mini':{'MiniUIResults-warmup':30,'MiniUIResults':10}}
  for scope,stems in inventory.items():
   with self.subTest(scope=scope),self.fixture(scope) as root:
    for stem,cap in stems.items():self.assertEqual(contract(scope,stem)['summary_cap'],cap)
  with self.fixture('iphone_se3') as root:
   records,raw=self.produce(root,'CompactPhoneUIResults','iphone_se3')
   records['CompactPhoneUIResults-summary-command.json'].update(timeout_seconds=10,state='timed_out',exit=124,elapsed_seconds=10.05)
   value=classify('iphone_se3','CompactPhoneUIResults',records,raw)
   self.assertFalse(value['acceptance']);self.assertEqual(value['summary_command'],'unqualified')
   self.assertEqual(value['native_summary'],'retained_unqualified')

 def test_manual_browser_image_rejects_wrong_stage_scope_type_and_source_cap(self):
  variants=(('iphone_se3','CompactPhoneUIResults-files',b'\xff\xd8valid'),
            ('ipad_mini','MiniUIResults-warmup',b'\xff\xd8valid'),
            ('iphone_se3','CompactPhoneUIResults',b'not JPEG'),
            ('iphone_se3','CompactPhoneUIResults',b'\xff\xd8'+b'x'*(500*1024)))
  for scope,stem,data in variants:
   with self.subTest(scope=scope,stem=stem,size=len(data)),self.fixture(scope) as root:
    self.produce(root,stem,scope)
    def runner(command,**kwargs):
     self.assertEqual(command[:3],['xcrun','xcresulttool','export'])
     folder=root/command[-1];(folder/'manual.jpg').write_bytes(data)
     (folder/'manifest.json').write_text(json.dumps([{'name':'privacy-browser-manual-review','exportedFileName':'manual.jpg'}]))
     return subprocess.CompletedProcess(command,0,'','')
    with self.assertRaises(ValueError):self.run_exporter(runner)
    self.assertFalse(list((root/'build/ios-platform-evidence').glob('*privacy-browser-manual-review*.jpg')))

 def test_exact_healthy_mini_host_export_lease_permits_only_its_bounded_read_only_export(self):
  with self.fixture() as root:
   self.mini_host_lease(root)
   self.assertFalse(export_blocked(route.current_identity()))
   for name in ('owned-process-cleanup.json','ipad-mini-inflight.json','fixture-query-inflight.json'):
    path=root/'build'/name;path.write_text('{"pending":true}')
    self.assertTrue(export_blocked(route.current_identity()));path.unlink()
   with patch.dict(os.environ,{'QRCATCHER_OWNED_CLEANUP_UNCONFIRMED':'true'}):self.assertTrue(export_blocked(route.current_identity()))

 def test_foreign_host_lease_pending_row_or_missing_clock_cannot_bypass_mini_barrier(self):
  for variant in ('owner','source','command','pending_row','late_export','missing_clock','duplicate'):
   with self.subTest(variant=variant),self.fixture() as root:
    host,state=self.mini_host_lease(root)
    if variant=='owner':host['owner_pid']+=1
    elif variant=='source':host['source']='c'*40
    elif variant=='command':host['command']=['foreign']
    elif variant=='pending_row':state['phases']['mini']['status']='row_running'
    elif variant=='late_export':state['phases']['export']['started']-=200;state['phases']['export']['deadline']-=200
    elif variant=='missing_clock':Path(os.environ['QRCATCHER_MINI_JOB_ORIGIN']).unlink()
    host_path=root/'build/ipad-mini-host-inflight.json';host_path.write_text(json.dumps(host))
    (root/'build/ipad-mini-job-state.json').write_text(json.dumps(state))
    if variant=='duplicate':host_path.write_text('{"phase":"host-export","phase":"foreign"}')
    self.assertTrue(export_blocked(route.current_identity()))

 def test_host_row_or_ledger_change_during_gate_validation_is_rejected(self):
  import ipad_mini_setup as mini
  for name in ('ipad-mini-host-inflight.json','ipad-mini-row-dispatched.json','ipad-mini-job-state.json'):
   with self.subTest(name=name),self.fixture() as root:
    self.mini_host_lease(root);actual=mini.read_regular;reads=0
    def changed(path,cap=16384):
     nonlocal reads
     data=actual(path,cap)
     if Path(path).name==name:
      reads+=1
      # Budget itself reads the ledger first; poison the last proof read.
      expected=3 if name=='ipad-mini-job-state.json' else 2
      if reads==expected:
       value=json.loads(data);value['source']='c'*40;Path(path).write_text(json.dumps(value))
     return data
    with patch.object(mini,'read_regular',side_effect=changed):self.assertTrue(export_blocked(route.current_identity()))

 def test_missing_or_failed_seed_cannot_qualify_a_later_photos_summary(self):
  for seed_exit in (None,13):
   with self.subTest(seed_exit=seed_exit),self.fixture() as root:
    self.produce(root,'MiniUIResults')
    if seed_exit is not None:
     seed=self.operation(['xcrun','simctl','addmedia',DEVICE,'Tests/Fixtures/unicode.png'],210,seed_exit)
     (root/'build/MiniUIResults-seed-command.json').write_text(json.dumps(seed))
     (root/'MiniUIResults-seed.log').write_text('known completed failed seed')
    self.run_exporter()
    value=json.loads((root/'build/ios-platform-evidence/manifest.json').read_text())
    self.assertFalse(value['selected_evidence']['photos_seed']['acceptance'])
    self.assertFalse(value['results']['ipad-mini']['selected_case_acceptance'])

 def test_selected_phone_ordinary_marks_largest_endpoints_not_selected(self):
  with self.fixture('iphone_se3') as root:
   self.produce(root,'CompactPhoneUIResults','iphone_se3')
   (root/'build/owned-process-cleanup.json').write_text('{"blocked":true}')
   self.run_exporter();value=json.loads((root/'build/ios-platform-evidence/manifest.json').read_text())
   self.assertEqual(value['missing_phone_result_endpoints'],[])
   self.assertEqual({row['checkpoint'] for row in value['not_selected']},{'phone-largest-history-result','phone-largest-history-result-top','phone-largest-history-result-end'})
   self.assertFalse(value['evidence_complete'])

 def test_selected_produced_files_and_photos_still_require_all_strict_audit_pairs(self):
  with self.fixture('iphone_se3') as root:
   for stem in ('CompactPhoneUIResults-files','CompactPhoneUIResults-imports'):self.produce(root,stem,'iphone_se3')
   (root/'build/owned-process-cleanup.json').write_text('{"blocked":true}')
   with self.assertRaises(SystemExit):self.run_exporter()
   value=json.loads((root/'build/ios-platform-evidence/manifest.json').read_text())
   self.assertEqual({row['result_label'] for row in value['missing_import_audit_pairs']},{'SE3-files','SE3-imports'})

 def test_legacy_default_inventory_and_endpoint_guard_remain(self):
  with self.fixture('iphone_se3') as root:
   os.environ['GITHUB_REF']='refs/heads/codex/apple-platforms';os.environ.pop('QRCATCHER_IOS_SUPPLEMENT_ONLY')
   result=root/'CompactPhoneUIResults.xcresult';result.mkdir();(result/'Info.plist').write_text('legacy owned metadata')
   def runner(command,**kwargs):
    if command[2]=='get':return subprocess.CompletedProcess(command,0,'{"result":"Passed"}','')
    Path(command[-1],'manifest.json').write_text('[]');return subprocess.CompletedProcess(command,0,'','')
   with patch('subprocess.check_output',return_value=SHA+'\n'),patch('subprocess.run',side_effect=runner):
    with self.assertRaisesRegex(SystemExit,'App-owned result endpoint evidence incomplete'):runpy.run_path(str(EXPORTER),run_name='__main__')
   value=json.loads((root/'build/ios-platform-evidence/manifest.json').read_text())
   self.assertNotIn('ipad-mini-warmup',value['results']);self.assertNotIn('not_selected',value)
   self.assertNotIn('selected_evidence',value);self.assertNotIn('diagnostic_only',value)
   self.assertEqual(value['missing_phone_result_endpoints'],[{'result_label':'SE3','missing':['app-owned result evidence mode and required pixels']}])


if __name__=='__main__':unittest.main()
