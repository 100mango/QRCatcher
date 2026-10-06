"""Actual Bash/Python closed executor regressions with explicit Apple doubles.

No Apple process, simulator service, provider or application runs in this suite.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import ios_original_supplement_route as route
import ipad_mini_setup as mini
import test_ipad_mini_setup as base

DEVICE=base.DEVICE
STUB=r'''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
name=Path(sys.argv[0]).name;args=sys.argv[1:]
with open(os.environ['APPLE_CALL_LOG'],'a') as f:f.write(json.dumps([name,args])+'\n')
if name=='xcodebuild':
 result=args[args.index('-resultBundlePath')+1]
 key='WARMUP_EXIT' if '-warmup.' in result else 'FILES_EXIT' if '-files.' in result else 'PHOTOS_EXIT' if '-imports.' in result or result in ('PadUIResults.xcresult','MiniUIResults.xcresult') else 'ORDINARY_EXIT'
 print('Explicit native command double; no app execution')
 print('X'*int(os.environ.get('NATIVE_LOG_BYTES','0')))
 raise SystemExit(int(os.environ.get(key,'0')))
if args==['simctl','list','-j']:
 print(json.dumps({'runtimes':[{'identifier':os.environ['RUNTIME'],'isAvailable':True}],
 'devicetypes':[{'identifier':os.environ['DEVICE_TYPE'],'name':'iPad mini (A17 Pro)'}],
 'devices':{os.environ['RUNTIME']:[]}}))
elif args[:2]==['simctl','create']:print(os.environ['DEVICE'])
elif args==['simctl','list','devices','available','-j']:
 counter=Path(os.environ['STATE_COUNTER']);index=int(counter.read_text()) if counter.exists() else 0;counter.write_text(str(index+1))
 states=['Shutdown']+json.loads(os.environ.get('HANDOFF_STATES','["Booted","Booted"]'))
 state=states[min(index,len(states)-1)]
 print(json.dumps({'devices':{os.environ['RUNTIME']:[{'udid':os.environ['DEVICE'],'name':'QRCatcher Mini 123-1',
 'deviceTypeIdentifier':os.environ['DEVICE_TYPE'],'isAvailable':True,'state':state}]}}))
elif args[:2]==['simctl','bootstatus']:
 print('Monitoring boot status for QRCatcher Mini 123-1 ('+os.environ['DEVICE']+').\nDevice already booted, nothing to do.\n')
elif args[:2]==['simctl','addmedia']:raise SystemExit(int(os.environ.get('SEED_STATUS','0')))
elif args[:2]==['simctl','get_app_container']:print(os.environ['SYNTHETIC_APP' if args[-1]=='app' else 'SYNTHETIC_DATA'])
elif args[:3]==['xcresulttool','get','test-results']:
 result=args[-1]
 count=2 if result in ('PhoneUIResults.xcresult','CompactPhoneUIResults.xcresult','PadUIResults-layout.xcresult') else 1
 key='WARMUP_EXIT' if '-warmup.' in result else 'FILES_EXIT' if '-files.' in result else 'PHOTOS_EXIT' if '-imports.' in result or result in ('PadUIResults.xcresult','MiniUIResults.xcresult') else 'ORDINARY_EXIT'
 failed=int(os.environ.get(key,'0'))!=0
 print(json.dumps({'result':'Failed' if failed else 'Passed','totalTestCount':count,'passedTests':count-int(failed),
 'failedTests':int(failed),'skippedTests':0,'expectedFailures':0,'runtimeWarnings':[],
 'devicesAndConfigurations':[{'device':{'deviceId':os.environ.get('SUMMARY_DEVICE',os.environ['DEVICE'])}}],
 'testFailures':[{'failureText':'Explicit finalized assertion double'}] if failed else []}))
'''
RECEIPT_DOUBLE='''
_actual_execute=execute
def execute(*args,**kwargs):
 code,tail,operation=_actual_execute(*args,**kwargs)
 command=args[0];target=os.environ.get('RECEIPT_TARGET','native')
 if (target=='native' and command[0]=='xcodebuild') or (target=='seed' and command[:3]==['xcrun','simctl','addmedia']):
  change=json.loads(os.environ['RECEIPT_CHANGE'])
  if change.pop('late',False):change['elapsed_seconds']=operation['timeout_seconds']+2.01
  operation.update(change)
 return code,tail,operation
'''


class SupplementExecutorTests(unittest.TestCase):
 @contextlib.contextmanager
 def fixture(self,scope):
  with tempfile.TemporaryDirectory(prefix='qr-supplement-executor-') as name:
   root=Path(name).resolve();(root/'build').mkdir();(root/'runner').mkdir()
   scripts=root/'scripts';scripts.mkdir()
   for source in (ROOT/'scripts').glob('*.py'):shutil.copyfile(source,scripts/source.name)
   shutil.copyfile(ROOT/'scripts/run_ios_platform_ui.sh',scripts/'run_ios_platform_ui.sh')
   for filename in (route.original.CANONICAL,route.original.WORKFLOW,route.WORKFLOW):
    target=root/filename;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/filename,target)
   fixture=root/'Tests/Fixtures';fixture.mkdir(parents=True);(fixture/'unicode.png').write_bytes(b'Explicit fixture routing bytes only')
   app=root/'synthetic-app';app.mkdir();data=root/'synthetic-data';data.mkdir()
   (app/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'100mango.QRCatcher','UIFileSharingEnabled':True,'LSSupportsOpeningDocumentsInPlace':True}))
   binary=root/'bin';binary.mkdir()
   for command in ('xcrun','xcodebuild'):(binary/command).write_text(STUB);(binary/command).chmod(0o755)
   env={**os.environ,'GITHUB_WORKSPACE':str(root),'GITHUB_SHA':base.SHA,'GITHUB_WORKFLOW_SHA':base.SHA,
    'GITHUB_REPOSITORY':'100mango/QRCatcher','GITHUB_REF':route.REF,'GITHUB_WORKFLOW_REF':route.WORKFLOW_REF,
    'GITHUB_EVENT_NAME':'push','GITHUB_JOB':'platform','RUNNER_OS':'macOS','RUNNER_ARCH':'ARM64',
    'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','EVIDENCE_SCOPE':scope,'IOS_FIRST_RELEASE_CANDIDATE_ONLY':'true',
    'QRCATCHER_IOS_SUPPLEMENT_ONLY':'true','GITHUB_ENV':str(root/'env'),'RUNNER_TEMP':str(root/'runner'),
    'QRCATCHER_OWNED_PROCESS_BARRIER':str(root/'build/owned-process-cleanup.json'),'DEVICE':DEVICE,
    'RUNTIME':base.RUNTIME,'DEVICE_TYPE':base.TYPE,'PATH':str(binary)+os.pathsep+os.environ['PATH'],
    'APPLE_CALL_LOG':str(root/'calls.jsonl'),'STATE_COUNTER':str(root/'states'),
    'SYNTHETIC_APP':str(app),'SYNTHETIC_DATA':str(data)}
   env.pop('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED',None)
   env.update(SIMULATOR_ID=DEVICE,COMPACT_SIMULATOR_ID=DEVICE,IPAD_SIMULATOR_ID=DEVICE,MINI_SIMULATOR_ID=DEVICE)
   yield root,env
 def invoke(self,root,env,result=None,kind=None):
  defaults={'iphone_pro':('PhoneUIResults.xcresult','QRCatcherUITests'),
   'iphone_se3':('CompactPhoneUIResults.xcresult','QRCatcherUITests'),
   'ipad_pro':('PadUIResults.xcresult','QRCatcherPadUITests'),
   'ipad_mini':('MiniUIResults.xcresult','QRCatcherPadUITests')}
  wanted=defaults[env['EVIDENCE_SCOPE']]
  return subprocess.run(['bash','scripts/run_ios_platform_ui.sh',DEVICE,result or wanted[0],kind or wanted[1]],
   cwd=root,env=env,capture_output=True,text=True,timeout=20)
 def calls(self,root):
  path=root/'calls.jsonl'
  return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
 def receipt_double(self,root):
  source=root/'scripts/watch_process.py';source.write_text(source.read_text()+'\nimport json\n'+RECEIPT_DOUBLE)
 def prepare_mini(self,root,env):
  prior=Path.cwd()
  with patch.dict(os.environ,env,clear=True):
   os.chdir(root)
   try:
    origin=root/'runner/qrcatcher-mini-123-1.json';env['QRCATCHER_MINI_JOB_ORIGIN']=str(origin)
    os.environ['QRCATCHER_MINI_JOB_ORIGIN']=str(origin)
    identity=mini.context()[1]
    origin.write_text(json.dumps({'version':1,**identity,'caps':mini.IOS_FIRST_CAPS,'started_monotonic':time.monotonic()}))
    budget=mini.Budget()
    for phase in ('prepare','build'):
     budget.enter(phase);budget.state['phases'][phase]['status']='completed';budget.persist()
   finally:os.chdir(prior)
  result=subprocess.run([sys.executable,'scripts/ipad_mini_setup.py','configure'],cwd=root,env=env,capture_output=True,text=True,timeout=10)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
  receipt=json.loads((root/'build/ipad-mini-owned-device.json').read_text())
  self.assertEqual(receipt['device'],DEVICE);self.assertTrue(receipt['absent_from_initial_inventory'])
  self.assertEqual(receipt['state'],'configured_shutdown_device_only')
  return receipt
 def test_actual_newref_prepare_retains_owned_provenance_and_builds_ios_only_prerequisite(self):
  # Run the actual controller -> Bash prepare -> owned prepared receipt ->
  # generator -> Debug build/package consumers. Apple/Git/binary bytes are
  # explicit existing doubles; this supplies no native compilation proof.
  from test_ios_only_release_package import IOSOnlyPackageTests
  owner=base.MiniSetupTests();owner.setUp();package=IOSOnlyPackageTests();package.setUp()
  try:
   env,log=owner.prepare_fixture();f=owner.f;package.hosted(ui_target=True)
   env.update(GITHUB_REF=route.REF,GITHUB_WORKFLOW_REF=route.WORKFLOW_REF,GITHUB_JOB='platform',
    EVIDENCE_SCOPE='ipad_mini',IOS_FIRST_RELEASE_CANDIDATE_ONLY='true',QRCATCHER_IOS_SUPPLEMENT_ONLY='true',
    RUNNER_OS='macOS',RUNNER_ARCH='ARM64',SYNTHETIC_IOS_PRODUCTS=str(package.xctestrun.parent))
   origin=json.loads(f.origin.read_text());origin['caps']=mini.IOS_FIRST_CAPS;f.origin.write_text(json.dumps(origin))
   compiler=f.root/'bin/xcodebuild';stub=compiler.read_text()
   anchor="elif name=='xcodebuild' and args==['-version']:print('Xcode 27.0\\nBuild version 27A266a')\n"
   self.assertEqual(stub.count(anchor),1)
   compiler.write_text(stub.replace(anchor,anchor+"elif name=='xcodebuild' and args[:1]==['build-for-testing']:\n shutil.copytree(os.environ['SYNTHETIC_IOS_PRODUCTS'],'build/iOS/Build/Products')\n print('Explicit compiler double with synthetic public-layout iOS products; no Apple compilation')\n",1))
   outputs=[]
   for phase in ('prepare','build'):
    command=[sys.executable]+(['-O'] if not __debug__ else [])+['scripts/ipad_mini_setup.py','phase',phase]
    result=subprocess.run(command,cwd=f.root,env=env,capture_output=True,text=True,timeout=100,start_new_session=True)
    outputs.append({'command':command,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    self.assertFalse((f.root/'build/ipad-mini-host-inflight.json').exists())
    self.assertNotIn('SHELL_ARGUMENT_ROUTING_PASS',result.stdout);self.assertNotIn('MINI_SYNTHETIC_UNIT_COMPLETED',result.stdout)
    for line in (f.root/'env').read_text().splitlines():
     key,value=line.split('=',1);env[key]=value
   provenance_raw=(f.root/route.original.RECEIPT).read_bytes();provenance=json.loads(provenance_raw)
   self.assertEqual(provenance['ref'],route.REF);self.assertTrue(provenance['diagnostic_only'])
   self.assertEqual(provenance['project'],route.PROJECT);self.assertEqual(provenance['tested_tree'],'b'*40)
   self.assertEqual(provenance['source_readback_phase'],'existing bounded managed Mini prepare HEAD/tree/diff')
   self.assertEqual(hashlib.sha256(provenance_raw).hexdigest(),env[route.original.INITIAL_HASH_KEY])
   ledger=json.loads((f.root/'build/ipad-mini-job-state.json').read_text());phases=ledger['phases']
   self.assertEqual(phases['prepare']['status'],'completed');self.assertEqual(phases['build']['status'],'completed')
   self.assertEqual([operation['cap'] for operation in phases['build']['operations']],[135,20])
   self.assertEqual(phases['build']['deadline'],phases['build']['started']+180)
   self.assertEqual(ledger['deadline_monotonic'],ledger['started_monotonic']+3000)
   self.assertFalse(ledger['full_job_accepted']);self.assertNotIn('mini',phases)
   project=f.root/route.PROJECT/'project.pbxproj'
   self.assertEqual(project.read_bytes(),(ROOT/route.PROJECT/'project.pbxproj').read_bytes())
   report=json.loads((f.root/'build/ios-first-debug-package.json').read_text())
   self.assertEqual(report['status'],'pass');self.assertEqual(report['scope'],'ios-only-debug-hosted-test-package')
   self.assertEqual(report['hosted_tests']['xctestrun']['binding']['host'],str(f.root/'build/iOS/Build/Products/Debug-iphonesimulator/QRCatcher.app'))
   calls=[json.loads(line) for line in log.read_text().splitlines()]
   self.assertIn(['xcodebuild',['-list','-project',route.PROJECT]],calls)
   builds=[args for name,args in calls if name=='xcodebuild' and args[:1]==['build-for-testing']]
   self.assertEqual(len(builds),1);self.assertIn(route.PROJECT,builds[0])
   self.assertFalse(any(name=='xcrun' and args[:1]==['simctl'] for name,args in calls))
   leases=[json.loads(line) for line in Path(str(log)+'.lease.jsonl').read_text().splitlines()]
   prepared=[row for row in leases if row['lease']['phase']=='host-prepare']
   self.assertTrue(prepared);self.assertEqual(len({row['sha256'] for row in prepared}),1)
   self.assertTrue(all(row['lease']['command']==['bash','scripts/ipad_mini_prepare.sh'] for row in prepared))
   self.assertTrue(any(row['lease']['phase']=='host-build' and row['lease']['command'][0]=='xcodebuild' for row in leases))
   workflow=(f.root/route.WORKFLOW).read_text();self.assertTrue(base.preflight_contract(workflow))
   prepare=(f.root/'scripts/ipad_mini_prepare.sh').read_text()
   self.assertNotIn('unittest discover',prepare)
   for name in base.UNITS:self.assertNotIn('Tests/Harness/'+name,prepare)
   print('ACTUAL_SUPPLEMENT_PREPARE_BUILD_INTEGRATION '+json.dumps({'classification':'Actual unchanged controller/Bash/generator/package flow with explicit Apple/Git/compiler/product doubles; no native run',
    'outputs':outputs,'provenance':provenance,'ledger':ledger,'debug_package':report,'apple_command_calls':calls,
    'observed_owned_host_leases':leases,'portable_modules_not_replayed_in_mini':list(base.UNITS),'native_execution':False,
    'project_sha256':hashlib.sha256(project.read_bytes()).hexdigest()},sort_keys=True),flush=True)
  finally:
   package.doCleanups();owner.tearDown()
 def test_actual_phones_select_exact_two_originals_then_independent_files_photos(self):
  for scope,file_cap in (('iphone_pro',360),('iphone_se3',240)):
   with self.subTest(scope=scope),self.fixture(scope) as (root,env):
    result=self.invoke(root,env);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    cases=[args for name,args in self.calls(root) if name=='xcodebuild']
    self.assertEqual(len(cases),3)
    self.assertEqual([arg for arg in cases[0] if arg.startswith('-only-testing:')],['-only-testing:'+value for value in route.PHONE_CHECKS])
    self.assertNotIn('-only-testing:QRCatcherUITests/QRCatcherUITests',cases[0])
    self.assertEqual([arg for arg in cases[1] if arg.startswith('-only-testing:')],['-only-testing:'+route.FILES])
    self.assertEqual([arg for arg in cases[2] if arg.startswith('-only-testing:')],['-only-testing:'+route.PHONE_PHOTOS])
    base_name='PhoneUIResults' if scope=='iphone_pro' else 'CompactPhoneUIResults'
    for stem,count,cap in ((base_name,2,570),(base_name+'-files',1,file_cap),(base_name+'-imports',1,360)):
     command=json.loads((root/'build'/(stem+'-command.json')).read_text());summary=json.loads((root/'build'/(stem+'-summary.json')).read_text())
     self.assertEqual(command['timeout_seconds'],cap);self.assertTrue(command['cleanup_confirmed'])
     self.assertEqual(summary['totalTestCount'],count);self.assertEqual(summary['devicesAndConfigurations'][0]['device']['deviceId'],DEVICE)
 def test_actual_phone_failed_selected_phase_retains_two_and_hardstops(self):
  with self.fixture('iphone_pro') as (root,env):
   result=self.invoke(root,{**env,'ORDINARY_EXIT':'65'});self.assertEqual(result.returncode,65,result.stdout+result.stderr)
   self.assertEqual(sum(name=='xcodebuild' for name,args in self.calls(root)),1)
   self.assertFalse(any('addmedia' in args or 'get_app_container' in args for name,args in self.calls(root)))
   summary=json.loads((root/'build/PhoneUIResults-summary.json').read_text());self.assertEqual((summary['totalTestCount'],summary['failedTests']),(2,1))
   self.assertFalse((root/'build/ios-import-continuation.json').exists())
 def test_actual_phone_failed_files_keeps_failed_receipt_and_attempts_photos(self):
  with self.fixture('iphone_pro') as (root,env):
   result=self.invoke(root,{**env,'FILES_EXIT':'65'});self.assertEqual(result.returncode,65,result.stdout+result.stderr)
   self.assertEqual(sum(name=='xcodebuild' for name,args in self.calls(root)),3)
   self.assertEqual(json.loads((root/'build/PhoneUIResults-files-summary.json').read_text())['failedTests'],1)
   self.assertEqual(json.loads((root/'build/PhoneUIResults-imports-summary.json').read_text())['passedTests'],1)
 def test_actual_phone_seed_timeout_retains_completed_checks_and_files(self):
  with self.fixture('iphone_se3') as (root,env):
   result=self.invoke(root,{**env,'SEED_STATUS':'124'});self.assertEqual(result.returncode,124,result.stdout+result.stderr)
   self.assertEqual(sum(name=='xcodebuild' for name,args in self.calls(root)),2)
   for stem in ('CompactPhoneUIResults','CompactPhoneUIResults-files'):
    self.assertTrue((root/(stem+'.log')).is_file());self.assertTrue((root/'build'/(stem+'-command.json')).is_file())
    self.assertGreater(json.loads((root/'build'/(stem+'-summary.json')).read_text())['passedTests'],0)
   self.assertFalse((root/'build/CompactPhoneUIResults-imports-summary.json').exists())
 def test_actual_pad_pro_preserves_original_layout_files_and_photos(self):
  with self.fixture('ipad_pro') as (root,env):
   result=self.invoke(root,env);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   cases=[args for name,args in self.calls(root) if name=='xcodebuild']
   self.assertEqual(len(cases),3);self.assertIn('-only-testing:QRCatcherUITests/QRCatcherPadUITests',cases[0])
   self.assertEqual(json.loads((root/'build/PadUIResults-layout-summary.json').read_text())['totalTestCount'],2)
 def test_actual_wrong_identity_flag_and_foreign_destination_refuse_before_any_command(self):
  changes=({'GITHUB_WORKFLOW_SHA':'b'*40},{'GITHUB_WORKFLOW_REF':'wrong'},
   {'GITHUB_REF':'refs/heads/codex/apple-platforms'},{'IOS_FIRST_RELEASE_CANDIDATE_ONLY':'false'},
   {'QRCATCHER_IOS_SUPPLEMENT_ONLY':'false'},{'SIMULATOR_ID':'11111111-2222-4333-8444-555555555555'})
  for change in changes:
   with self.subTest(change=change),self.fixture('iphone_pro') as (root,env):
    self.assertNotEqual(self.invoke(root,{**env,**change}).returncode,0);self.assertEqual(self.calls(root),[])
 def test_actual_foreign_summary_device_stops_before_fixture_and_seed(self):
  with self.fixture('iphone_pro') as (root,env):
   result=self.invoke(root,{**env,'SUMMARY_DEVICE':'11111111-2222-4333-8444-555555555555'})
   self.assertEqual(result.returncode,126,result.stdout+result.stderr)
   self.assertFalse(any('addmedia' in args or 'get_app_container' in args for name,args in self.calls(root)))
   self.assertTrue((root/'build/PhoneUIResults-summary.json').is_file())
 def test_actual_bash_reported_late_unknown_or_unclean_native_receipt_refuses_queries(self):
  # Alter only the returned ownership receipt in the disposable process
  # double. Bash and its production receipt validator execute unchanged.
  for scope in ('iphone_pro','ipad_mini'):
   for change in ({'late':True},{'cleanup_confirmed':False},{'state':'unknown'}):
    with self.subTest(scope=scope,change=change),self.fixture(scope) as (root,env):
     if scope=='ipad_mini':self.prepare_mini(root,env)
     self.receipt_double(root)
     result=self.invoke(root,{**env,'RECEIPT_CHANGE':json.dumps(change)})
     self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
     calls=self.calls(root);native=next(index for index,(name,args) in enumerate(calls) if name=='xcodebuild')
     self.assertEqual(native,len(calls)-1)
     stem='PhoneUIResults' if scope=='iphone_pro' else 'MiniUIResults-warmup'
     self.assertTrue((root/'build'/(stem+'-command.json')).is_file())
     self.assertFalse((root/'build'/(stem+'-summary.json')).exists())
 def test_actual_phone_seed_late_unknown_or_unclean_receipt_retains_checks_and_files(self):
  for change in ({'late':True},{'cleanup_confirmed':False},{'state':'timed_out'}):
   with self.subTest(change=change),self.fixture('iphone_pro') as (root,env):
    self.receipt_double(root)
    result=self.invoke(root,{**env,'RECEIPT_TARGET':'seed','RECEIPT_CHANGE':json.dumps(change)})
    self.assertEqual(result.returncode,126,result.stdout+result.stderr)
    calls=self.calls(root);seed=next(index for index,(name,args) in enumerate(calls) if 'addmedia' in args)
    self.assertEqual(seed,len(calls)-1)
    for stem,count in (('PhoneUIResults',2),('PhoneUIResults-files',1)):
     self.assertEqual(json.loads((root/'build'/(stem+'-summary.json')).read_text())['passedTests'],count)
    self.assertTrue((root/'build/PhoneUIResults-seed-command.json').is_file())
    setup=json.loads((root/'build/ios-platform-setup.json').read_text())
    self.assertEqual(setup['photo_seed_exit'],0);self.assertEqual(setup['photo_import_gate'],'blocked_or_not_requested')
    self.assertEqual(setup['real_photo_case_exit'],-1)
 def test_actual_stale_selected_evidence_refuses_before_phone_or_mini_launch(self):
  for scope in ('iphone_pro','ipad_mini'):
   with self.subTest(scope=scope),self.fixture(scope) as (root,env):
    if scope=='ipad_mini':self.prepare_mini(root,env)
    before=self.calls(root)
    stem='PhoneUIResults' if scope=='iphone_pro' else 'MiniUIResults-warmup'
    (root/'build'/(stem+'-summary.json')).write_text('{"stale":true}')
    result=self.invoke(root,env);self.assertNotEqual(result.returncode,0)
    self.assertEqual(self.calls(root),before)
 def test_actual_new_owned_mini_runs_only_warmup_and_photos_same_uuid_old_caps(self):
  for states in (['Booted','Booted'],['Shutdown','Shutdown']):
   with self.subTest(states=states),self.fixture('ipad_mini') as (root,env):
    env={**env,'HANDOFF_STATES':json.dumps(states),'NATIVE_LOG_BYTES':'70000'};receipt=self.prepare_mini(root,env)
    result=self.invoke(root,env);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    calls=self.calls(root);cases=[args for name,args in calls if name=='xcodebuild']
    self.assertEqual(len(cases),2)
    self.assertEqual([arg for arg in cases[0] if arg.startswith('-only-testing:')],['-only-testing:'+route.MINI_WARMUP])
    self.assertEqual([arg for arg in cases[1] if arg.startswith('-only-testing:')],['-only-testing:'+route.PAD_PHOTOS])
    self.assertTrue(all('platform=iOS Simulator,id='+DEVICE in args for args in cases))
    self.assertFalse(any('get_app_container' in args or any('testRealFiles' in arg for arg in args) for name,args in calls))
    state=json.loads((root/'build/ipad-mini-job-state.json').read_text());phase=state['phases']['mini']
    self.assertEqual(phase['deadline'],receipt['row_deadline_monotonic']);self.assertEqual(state['deadline_monotonic'],state['started_monotonic']+3000)
    self.assertEqual([op['cap'] for op in phase['operations'] if op['command'][:2]==['xcodebuild','test-without-building']],[480,360])
    self.assertEqual([op['cap'] for op in phase['operations'] if op['command'][:3]==['xcrun','xcresulttool','get']],[30,10])
    self.assertEqual([op['cap'] for op in phase['operations'] if op['command'][:3]==['xcrun','simctl','addmedia']],[210])
    self.assertEqual([op['cap'] for op in phase['operations'] if op['command'][:3]==['xcrun','simctl','bootstatus']],[] if states[0]=='Booted' else [210,90])
    self.assertEqual(set(phase['state_handoffs']),{'before_first_layout','before_photos_seed'})
    self.assertEqual(phase['row_admissions']['configure']['required_seconds'],2152)
    self.assertGreater((root/'MiniUIResults-warmup.log').stat().st_size,70000)
    setup=json.loads((root/'build/ios-platform-setup.json').read_text())
    self.assertEqual(setup['not_selected'],['layout','files']);self.assertEqual(setup['real_files_case_exit'],-1)
    self.assertEqual(setup['layout_and_real_picker_cancel_exit'],-1);self.assertEqual(setup['unexecuted'],[])
    self.assertFalse(setup['full_original_row_accepted']);self.assertFalse(setup['full_job_accepted'])
 def test_actual_mini_seed_timeout_preserves_completed_warmup_without_device_queries(self):
  with self.fixture('ipad_mini') as (root,env):
   self.prepare_mini(root,env);result=self.invoke(root,{**env,'SEED_STATUS':'124'})
   self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
   calls=self.calls(root);seed=next(index for index,(name,args) in enumerate(calls) if 'addmedia' in args)
   self.assertEqual(seed,len(calls)-1)
   self.assertTrue((root/'MiniUIResults-warmup.log').is_file());self.assertTrue((root/'build/MiniUIResults-warmup-command.json').is_file())
   self.assertEqual(json.loads((root/'build/MiniUIResults-warmup-summary.json').read_text())['passedTests'],1)
   setup=json.loads((root/'build/ios-platform-setup.json').read_text())
   self.assertEqual(setup['selected_picker_warmup_exit'],0);self.assertEqual(setup['seed_attempts'],1)
   self.assertEqual(setup['photo_seed_exit'],124);self.assertEqual(setup['real_photo_case_exit'],-1)
 def test_actual_mini_completed_warmup_failure_retains_one_case_and_stops(self):
  with self.fixture('ipad_mini') as (root,env):
   self.prepare_mini(root,env);result=self.invoke(root,{**env,'WARMUP_EXIT':'65'})
   self.assertEqual(result.returncode,65,result.stdout+result.stderr)
   self.assertEqual(sum(name=='xcodebuild' for name,args in self.calls(root)),1)
   self.assertFalse(any('addmedia' in args for name,args in self.calls(root)))
   self.assertEqual(json.loads((root/'build/MiniUIResults-warmup-summary.json').read_text())['failedTests'],1)
   setup=json.loads((root/'build/ios-platform-setup.json').read_text())
   self.assertEqual(setup['selected_picker_warmup_exit'],65);self.assertEqual(setup['unexecuted'],['photos'])
 def test_actual_mini_configuration_requires_both_exact_flags_before_process(self):
  for change in ({'QRCATCHER_IOS_SUPPLEMENT_ONLY':'false'},{'IOS_FIRST_RELEASE_CANDIDATE_ONLY':'false'},
   {'GITHUB_WORKFLOW_REF':'wrong'}):
   with self.subTest(change=change),self.fixture('ipad_mini') as (root,env):
    result=subprocess.run([sys.executable,'scripts/ipad_mini_setup.py','configure'],cwd=root,env={**env,**change},capture_output=True,text=True,timeout=10)
    self.assertNotEqual(result.returncode,0);self.assertEqual(self.calls(root),[])
 def test_actual_mini_unknown_state_refuses_before_warmup(self):
  with self.fixture('ipad_mini') as (root,env):
   self.prepare_mini(root,env);result=self.invoke(root,{**env,'HANDOFF_STATES':'["Booting","Booted"]'})
   self.assertNotEqual(result.returncode,0);self.assertFalse(any(name=='xcodebuild' for name,args in self.calls(root)))
 def test_actual_mini_inherited_cleanup_refuses_before_any_new_command(self):
  with self.fixture('ipad_mini') as (root,env):
   self.prepare_mini(root,env);before=self.calls(root)
   (root/'build/owned-process-cleanup.json').write_text('{"blocked":true}')
   result=self.invoke(root,env);self.assertNotEqual(result.returncode,0);self.assertEqual(self.calls(root),before)
 def test_mini_late_or_unclean_completed_warmup_never_queries_summary_or_seed(self):
  for change in ({'elapsed_seconds':482.01},{'cleanup_confirmed':False},{'state':'timed_out','exit':124}):
   with self.subTest(change=change),self.fixture('ipad_mini') as (root,env):
    self.prepare_mini(root,env);prior=Path.cwd()
    with patch.dict(os.environ,env,clear=True):
     os.chdir(root)
     try:
      budget=mini.Budget();calls=[]
      def executor(command,cap,**kwargs):
       calls.append(command)
       if command[:3]==['xcrun','simctl','list']:
        raw=json.dumps({'devices':{base.RUNTIME:[{'udid':DEVICE,'name':'QRCatcher Mini 123-1','deviceTypeIdentifier':base.TYPE,'isAvailable':True,'state':'Booted'}]}})
       else:raw='Explicit bounded completed command double'
       operation={'command':command,'timeout_seconds':cap,'state':'completed','exit':0,'cleanup_confirmed':True,'elapsed_seconds':.01,'output_bytes':len(raw.encode())}
       if command[0]=='xcodebuild':operation.update(change)
       return operation['exit'],raw,operation
      with self.assertRaises(ValueError):mini.row([DEVICE,'MiniUIResults.xcresult','QRCatcherPadUITests'],budget,executor)
      self.assertFalse(any(command[:3]==['xcrun','xcresulttool','get'] or 'addmedia' in command for command in calls))
      self.assertTrue((root/'build/MiniUIResults-warmup-command.json').is_file())
     finally:
      mini._ACTIVE=None;mini._ROW_LEASE=None;os.chdir(prior)


if __name__=='__main__':unittest.main()
