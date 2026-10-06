"""Closed staged iOS scope, actual managed prepare, and bounded pure receipts.

Apple commands below are explicit doubles; this supplies no native proof.
"""
import ast
import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import ios_original_release_route as route
import ipad_mini_setup as mini
import test_ipad_mini_setup as base
import ios_import_continuation as continuation

SHA='a'*40
TREE='b'*40


class OriginalIOSRouteTests(unittest.TestCase):
 def setUp(self):
  self.canonical=(ROOT/route.CANONICAL).read_text()
  self.workflow=route.render_workflow(self.canonical)
  self.env={'GITHUB_REPOSITORY':route.REPOSITORY,'GITHUB_SHA':SHA,'GITHUB_WORKFLOW_SHA':SHA,
   'GITHUB_REF':route.REF,'GITHUB_WORKFLOW_REF':route.WORKFLOW_REF,'GITHUB_EVENT_NAME':'push',
   'IOS_FIRST_RELEASE_CANDIDATE_ONLY':'true','RUNNER_OS':'macOS','RUNNER_ARCH':'ARM64',
   'GITHUB_JOB':'platform','EVIDENCE_SCOPE':'ipad_mini','GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}
 @contextlib.contextmanager
 def fixture(self,job='platform',scope='ipad_mini'):
  with tempfile.TemporaryDirectory(prefix='qr-ios-original-') as name:
   root=Path(name).resolve();(root/'build').mkdir();before=Path.cwd()
   for path,text in ((route.CANONICAL,self.canonical),(route.WORKFLOW,self.workflow)):
    target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
   env={**self.env,'GITHUB_JOB':job,'EVIDENCE_SCOPE':scope,'GITHUB_WORKSPACE':str(root),
    'GITHUB_ENV':str(root/'env'),'QRCATCHER_OWNED_PROCESS_BARRIER':str(root/'build/owned-process-cleanup.json'),
    'PATH':os.environ.get('PATH',os.defpath)}
   with patch.dict(os.environ,env,clear=True):
    os.chdir(root)
    try:yield root
    finally:os.chdir(before)
 def marker(self,root):
  path=root/'build/ipad-mini-host-inflight.json'
  path.write_text(json.dumps({'source':SHA,'workflow_sha':SHA,'run_id':'123','run_attempt':'1',
   'scope':'ipad_mini','phase':'host-prepare','owner_pid':os.getpid(),'command':['bash','scripts/ipad_mini_prepare.sh']}))
  return path
 def test_closed_four_profiles_one_slot_and_package_scope(self):
  with self.fixture():record=route.current_identity()
  self.assertEqual(record['selected_scopes'],['iphone_pro','iphone_se3','ipad_pro','ipad_mini'])
  self.assertEqual(record['maximum_simultaneous_slots'],1)
  self.assertFalse(record['cancel_in_progress']);self.assertFalse(record['shipping_watch_requested'])
  self.assertFalse(record['release_qualification']);self.assertTrue(record['release_candidate_only'])
  self.assertEqual(record['required_phone_cases'],{'ordinary':9,'files':1,'photos':1})
  self.assertEqual(record['required_pad_cases'],{'layout':2,'files':1,'photos':1})
  self.assertEqual(record['required_unit_cases'],30)
  self.assertEqual(record['preflight_evidence_limit_bytes']+record['selected_runtime_evidence_limit_bytes'],9000000)
  self.assertIn('max-parallel: 1',self.workflow)
 def test_same_head_full_portable_preflight_dependency_preserved(self):
  self.assertTrue(base.preflight_contract(self.workflow))
  self.assertEqual(hashlib.sha256(self.canonical.encode()).hexdigest(),route.CANONICAL_SHA256)
  self.assertIn('compile_ios_original_preflight.py',self.workflow)
  self.assertIn('always() && steps.ios_package_evidence.outcome',self.workflow)
 def test_selected_native_step_bodies_only_change_project_identity(self):
  _,platform=route.job_parts(self.canonical);_,old,_=route.split_platform(platform)
  _,platform=route.job_parts(self.workflow);_,new,_=route.split_platform(platform)
  self.assertEqual(tuple(route.step_name(s) for s in new),route.SELECTED_STEPS)
  special={'Capture original Mini job clock before checkout','Verify exact source and stable toolchain',
   'Compile iOS tests before this device boots','Retain small phone and iPad evidence','Summarize executed evidence',*route.SOURCE_DEPENDENT_STEPS}
  for step in old:
   name=route.step_name(step)
   if name in route.SELECTED_STEPS and name not in special:
    expected=step.replace('-project QRCatcher.xcodeproj','-project '+route.PROJECT)
    expected=expected.replace('      timeout-minutes: 27\n','      timeout-minutes: 32\n')
    self.assertIn(expected,new,name)
  for forbidden in ('Run watchOS','Run native tvOS','Run native Vision','Sandbox UI gate'):
   self.assertNotIn(forbidden,self.workflow)
  self.assertNotIn('requires successful Mac XCTest',self.workflow)
  self.assertIn('Original iPhone/iPad qualification requires this exact isolated app/archive',self.workflow)
  for step in new:
   if route.step_name(step) in route.SOURCE_DEPENDENT_STEPS:
    self.assertIn("steps.ios_original_source.outcome == 'success'",step)
    old_step=next(s for s in old if route.step_name(s)==route.step_name(step))
    if route.step_name(step)!='Compile iOS tests before this device boots':
     self.assertEqual(step.split('      run:',1)[1],old_step.split('      run:',1)[1].replace('-project QRCatcher.xcodeproj','-project '+route.PROJECT))
 def test_canonical_or_route_mutation_rejected(self):
  with self.assertRaises(ValueError):route.render_workflow(self.canonical+'\n')
  with self.fixture() as root:
   (root/route.WORKFLOW).write_text(self.workflow.replace('max-parallel: 1','max-parallel: 2'))
   with self.assertRaises(ValueError):route.current_identity()
 def test_missing_wrong_or_foreign_identity_refuses(self):
  changes={'GITHUB_REPOSITORY':'another/repo','GITHUB_SHA':'a'*39,'GITHUB_WORKFLOW_SHA':'b'*40,
   'GITHUB_REF':'refs/heads/codex/apple-platforms','GITHUB_WORKFLOW_REF':'wrong',
   'GITHUB_EVENT_NAME':'workflow_dispatch','IOS_FIRST_RELEASE_CANDIDATE_ONLY':'false',
   'RUNNER_OS':'Linux','RUNNER_ARCH':'X64','GITHUB_JOB':'other','EVIDENCE_SCOPE':'macos',
   'GITHUB_RUN_ID':'0','GITHUB_RUN_ATTEMPT':'-1'}
  for key,value in changes.items():
   with self.subTest(key=key),self.fixture(),patch.dict(os.environ,{key:value}):
    with self.assertRaises(ValueError):route.current_identity()
 def test_preflight_requires_empty_scope(self):
  with self.fixture('preflight',''):self.assertEqual(route.current_identity()['job'],'preflight')
  with self.fixture('preflight','ipad_mini'),self.assertRaises(ValueError):route.current_identity()
 def test_all_mini_selectors_and_clocks_explicitly_bound(self):
  with self.fixture():
   self.assertTrue(mini.ios_first_profile());self.assertTrue(mini.extended_mini_profile())
   self.assertEqual(mini.mini_project(),route.PROJECT);self.assertEqual(mini.job_ledger_limit(),32768)
   self.assertEqual(mini.result_summary_limit('MiniUIResults-layout.xcresult'),30)
   self.assertEqual(mini.result_summary_limit('MiniUIResults-files.xcresult'),10)
   self.assertEqual(mini.result_summary_limit('MiniUIResults.xcresult'),10)
   self.assertIn(route.PROJECT,mini.test_command(base.DEVICE,mini.LAYOUT,'MiniUIResults-layout.xcresult'))
  self.assertEqual(sum(mini.DIAGNOSTIC_CAPS.values()),3000);self.assertEqual(mini.DIAGNOSTIC_CAPS['mini'],1920)
  self.assertIn("'checkout_post':60",self.workflow);self.assertIn("'mini':1920",self.workflow)
 def test_canonical_and_previous_mini_project_clocks_stay_explicit(self):
  with patch.dict(os.environ,{'GITHUB_REF':'refs/heads/codex/apple-platforms'}):
   self.assertEqual(mini.mini_project(),'QRCatcher.xcodeproj');self.assertEqual(mini.job_ledger_limit(),16384)
   self.assertEqual(mini.result_summary_limit('MiniUIResults-layout.xcresult'),10)
  self.assertEqual(sum(mini.CAPS.values()),2700);self.assertEqual(mini.CAPS['mini'],1620)
 def test_managed_prepare_lease_and_receipt_no_process(self):
  with self.fixture() as root,patch.object(route,'execute') as execute:
   marker=self.marker(root);before=marker.read_bytes();inode=marker.stat().st_ino
   record=route.prepared(SHA,TREE)
   self.assertEqual(record['tested_tree'],TREE);self.assertEqual(marker.read_bytes(),before)
   self.assertEqual(marker.stat().st_ino,inode);execute.assert_not_called()
   with self.assertRaises(ValueError):route.source_readback(SHA)
   execute.assert_not_called()
 def test_missing_wrong_or_changing_prepare_marker_refuses(self):
  with self.fixture() as root,patch.object(route,'execute') as execute:
   with self.assertRaises(OSError):route.prepared(SHA,TREE)
   marker=self.marker(root);value=json.loads(marker.read_text());value['owner_pid']=True;marker.write_text(json.dumps(value))
   with self.assertRaises(ValueError):route.prepared(SHA,TREE)
   self.marker(root);original=route.write_initial
   def changed(*args):result=original(*args);marker.write_text('{}');return result
   with patch.object(route,'write_initial',side_effect=changed),self.assertRaises(ValueError):route.prepared(SHA,TREE)
   execute.assert_not_called()
 def test_initial_retention_keeps_uncertainty_no_process(self):
  with self.fixture() as root:
   self.marker(root);route.prepared(SHA,TREE);(root/'build/ios-platform-evidence').mkdir()
   os.environ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED']='true'
   with patch.object(route,'execute') as execute:record=route.retain_prepared();execute.assert_not_called()
   self.assertTrue(record['retention_verification']['device_barrier_observed'])
   self.assertFalse(record['retention_verification']['fresh_source_readback_performed'])
   self.assertFalse(record['release_qualification'])
 def test_wrong_receipt_hash_run_or_tree_refuses(self):
  with self.fixture() as root:
   self.marker(root);route.prepared(SHA,TREE);(root/'build/ios-platform-evidence').mkdir()
   for key,value in ((route.INITIAL_HASH_KEY,'c'*64),('GITHUB_RUN_ATTEMPT','2')):
    with patch.dict(os.environ,{key:value}),self.assertRaises(ValueError):route.retain_prepared()
 def test_nonmini_readback_requires_timely_clean_actual_checkout(self):
  replies=[SHA,TREE,'',''];op={'state':'completed','cleanup_confirmed':True,'elapsed_seconds':.1}
  with self.fixture('platform','iphone_pro'),patch.object(route,'execute',side_effect=[(0,v,dict(op)) for v in replies]) as execute:
   self.assertEqual(route.source_readback(SHA),TREE);self.assertEqual(execute.call_count,4)
  for change in ({'state':'unknown'},{'cleanup_confirmed':False},{'elapsed_seconds':7.01}):
   with self.subTest(change=change),self.fixture('platform','iphone_pro'),patch.object(route,'execute',return_value=(0,SHA,{**op,**change})) as execute:
    with self.assertRaises(ValueError):route.source_readback(SHA)
    self.assertEqual(execute.call_count,1)
 def test_complete_preflight_evidence_is_pure_bounded_source_bound(self):
  with self.fixture('preflight','') as root:
   route.write_initial(route.current_identity(),TREE,'bounded initial original iOS HEAD/tree/diff/status')
   folder=root/'build/ios-original-preflight';folder.mkdir();(folder/'summary.json').write_text('{"passed":true}')
   for name in ('debug-build','debug-package','release-archive','release-package'):(folder/(name+'.log')).write_text('Synthetic returned phase\n')
   for name in ('debug','release'):(root/('build/ios-first-'+name+'-package.json')).write_text('{"passed":true}')
   os.environ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED']='true'
   with patch.object(route,'execute') as execute:result=route.collect_preflight();execute.assert_not_called()
   self.assertTrue(result['evidence_complete']);self.assertTrue(result['owned_process_uncertainty_observed'])
   self.assertFalse(result['observations_qualify_release']);self.assertEqual(len(result['files']),8)
   self.assertLess(sum(p.stat().st_size for p in (root/'build/ios-original-preflight-evidence').iterdir()),1000000)
 def test_missing_preflight_outputs_stay_explicit_incomplete(self):
  with self.fixture('preflight',''):
   route.write_initial(route.current_identity(),TREE,'bounded initial original iOS HEAD/tree/diff/status')
   result=route.collect_preflight();self.assertFalse(result['evidence_complete']);self.assertEqual(len(result['missing']),7)
 def test_preflight_symlink_or_oversize_refuses(self):
  for linked in (False,True):
   with self.subTest(linked=linked),self.fixture('preflight','') as root:
    route.write_initial(route.current_identity(),TREE,'bounded initial original iOS HEAD/tree/diff/status')
    target=root/'build/ios-first-debug-package.json'
    if linked:target.symlink_to(root/route.RECEIPT)
    else:target.write_bytes(b'x'*(64*1024+1))
    with self.assertRaises(ValueError):route.collect_preflight()
 def test_phone_continuation_uses_exact_profile_project(self):
  with self.fixture('platform','iphone_pro'):
   command=continuation.expected_command(base.DEVICE)
   self.assertIn(route.PROJECT,command);self.assertIn('-only-testing:QRCatcherUITests/QRCatcherUITests',command)
  with patch.dict(os.environ,{'GITHUB_REF':'refs/heads/codex/apple-platforms'}):
   self.assertIn('QRCatcher.xcodeproj',continuation.expected_command(base.DEVICE))
 def test_complete_newprofile_mini_row_keeps_four_cases_and_failed_files(self):
  for failed_files in (False,True):
   with self.subTest(failed_files=failed_files):
    f=base.Fixture()
    try:
     for path,text in ((route.CANONICAL,self.canonical),(route.WORKFLOW,self.workflow)):
      target=f.root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
     os.environ.update(self.env)
     value=json.loads(f.origin.read_text());value['caps']=mini.DIAGNOSTIC_CAPS;f.origin.write_text(json.dumps(value))
     f.budget.path.unlink();f.budget=mini.Budget(f.clock)
     for phase in ('prepare','build'):
      f.budget.enter(phase);f.budget.state['phases'][phase]['status']='completed';f.budget.persist()
     f.configure()
     f.readback_edit=lambda value:value['devices'][base.RUNTIME][0].update(state='Booted')
     f.file_exit=65 if failed_files else 0
     self.assertEqual(f.row(),65 if failed_files else 0)
     self.assertEqual(f.setup()['unexecuted'],[]);self.assertEqual(f.setup()['real_photo_case_exit'],0)
     self.assertEqual(f.setup()['real_files_case_exit'],65 if failed_files else 0)
     cases=[(command,cap) for command,cap in f.calls if command[:2]==['xcodebuild','test-without-building']]
     self.assertEqual([cap for command,cap in cases],[480,240,360])
     self.assertTrue(all(route.PROJECT in command for command,cap in cases))
     summaries=[cap for command,cap in f.calls if command[:3]==['xcrun','xcresulttool','get']]
     self.assertEqual(summaries,[30,10,10]);self.assertFalse(f.setup()['full_job_accepted'])
    finally:f.close()
 def test_actual_nonmini_shell_profiles_project_cases_and_failure_fences(self):
  source=ast.parse((ROOT/'Tests/Harness/test_ios_launcher.py').read_text())
  assignment=next(n for n in ast.walk(source) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='stub' for t in n.targets))
  stub=ast.literal_eval(assignment.value)
  for scope,test_class,result_name in [('iphone_pro','QRCatcherUITests','PhoneUIResults.xcresult'),
    ('iphone_se3','QRCatcherUITests','CompactPhoneUIResults.xcresult'),('ipad_pro','QRCatcherPadUITests','PadUIResults.xcresult')]:
   for file_exit,barrier in ((0,False),(65,False),(0,True)):
    with self.subTest(scope=scope,file_exit=file_exit,barrier=barrier),self.fixture('platform',scope) as root:
     scripts=root/'scripts';scripts.mkdir()
     for name in ('run_ios_platform_ui.sh','run_bounded.py','watch_process.py','owned_process_group.py',
       'owned_process_barrier.py','atomic_json.py','stage_owned_import_fixture.py','fixture_query_guard.py',
       'ios_import_continuation.py','ios_original_release_route.py','diagnostic_mini_managed_route.py'):
      shutil.copyfile(ROOT/'scripts'/name,scripts/name)
     binary=root/'bin';binary.mkdir()
     for name in ('xcrun','xcodebuild'):(binary/name).write_text(stub);(binary/name).chmod(0o755)
     app=root/'synthetic-app';app.mkdir();data=root/'synthetic-data';data.mkdir()
     import plistlib
     (app/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'100mango.QRCatcher','UIFileSharingEnabled':True,'LSSupportsOpeningDocumentsInPlace':True}))
     fixtures=root/'Tests/Fixtures';fixtures.mkdir(parents=True);(fixtures/'unicode.png').write_bytes(b'Explicit command-routing bytes only')
     env={**os.environ,'PATH':str(binary)+os.pathsep+os.environ['PATH'],'TEST_STATUS':'0','SEED_STATUS':'0',
      'FILE_STATUS':str(file_exit),'PHOTO_STATUS':'0','BARRIER_AFTER_FILES':str(barrier).lower(),
      'OBSERVED_COMMAND':str(root/'calls.json'),'SYNTHETIC_APP':str(app),'SYNTHETIC_DATA':str(data)}
     result=subprocess.run(['bash','scripts/run_ios_platform_ui.sh',base.DEVICE,result_name,test_class],
      cwd=root,env=env,capture_output=True,text=True,timeout=20)
     self.assertEqual(result.returncode,126 if barrier else file_exit,result.stdout+result.stderr)
     rows=json.loads((root/'calls.json').read_text());cases=[r['args'] for r in rows if r['tool']=='xcodebuild']
     self.assertEqual(len(cases),2 if barrier else 3);self.assertTrue(all(route.PROJECT in args for args in cases))
     self.assertTrue(any('testRealFilesImportAndReopen' in arg for arg in cases[1]))
     self.assertEqual(sum('addmedia' in r['args'] for r in rows),0 if barrier else 1)
     if not barrier:self.assertTrue(any('testRealPhoto' in arg for arg in cases[2]))
 def test_default_launcher_fixture_owns_ref_despite_outer_ios_candidate_environment(self):
  path=ROOT/'Tests/Harness/test_ios_launcher.py';source=path.read_text();tree=ast.parse(source)
  functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='launcher_fixture_environment']
  self.assertEqual(len(functions),1)
  calls=[n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='fixture_env' for t in n.targets)]
  self.assertEqual(len(calls),1)
  self.assertEqual(ast.dump(calls[0].value),ast.dump(ast.parse('launcher_fixture_environment(os.environ,folder)',mode='eval').body))
  # Execute only the actual pure environment constructor. Complete discovery
  # already runs all original33 Bash scenarios under this same outer CI ref.
  namespace={};exec(compile(ast.Module(body=functions,type_ignores=[]),str(path),'exec'),namespace)
  environment={'GITHUB_REF':route.REF,'IOS_FIRST_RELEASE_CANDIDATE_ONLY':'true',
   'GITHUB_WORKFLOW_REF':route.WORKFLOW_REF,'GITHUB_JOB':'preflight',
   'GITHUB_WORKSPACE':'/outer/workspace','GITHUB_ENV':'/outer/job-env',
   'QRCATCHER_OWNED_CLEANUP_UNCONFIRMED':'true','EVIDENCE_SCOPE':'ipad_mini','PATH':'/owned/path'}
  original=dict(environment)
  with tempfile.TemporaryDirectory() as name:
   folder=Path(name).resolve();actual=namespace['launcher_fixture_environment'](environment,folder)
   self.assertEqual(actual['GITHUB_REF'],'refs/heads/codex/apple-platforms')
   self.assertEqual(actual['GITHUB_WORKSPACE'],str(folder));self.assertEqual(actual['GITHUB_ENV'],str(folder/'fixture-github-env'))
   self.assertEqual(actual['PATH'],'/owned/path');self.assertEqual(actual['GITHUB_WORKFLOW_REF'],route.WORKFLOW_REF)
   self.assertTrue(all(k not in actual for k in ('IOS_FIRST_RELEASE_CANDIDATE_ONLY','QRCATCHER_OWNED_CLEANUP_UNCONFIRMED','EVIDENCE_SCOPE')))
  self.assertEqual(environment,original)
 def test_actual_newprofile_host_prepare_preserves_marker_and_default_dependency(self):
  owner=base.MiniSetupTests();owner.setUp()
  try:
   env,log=owner.prepare_fixture();f=owner.f
   env.update(self.env,GITHUB_WORKSPACE=str(f.root),GITHUB_ENV=str(f.root/'env'))
   value=json.loads(f.origin.read_text());value['caps']=mini.DIAGNOSTIC_CAPS;f.origin.write_text(json.dumps(value))
   command=[sys.executable]+(['-O'] if not __debug__ else [])+['scripts/ipad_mini_setup.py','phase','prepare']
   result=subprocess.run(command,cwd=f.root,env=env,capture_output=True,text=True,timeout=100,start_new_session=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   self.assertFalse((f.root/'build/ipad-mini-host-inflight.json').exists())
   state=json.loads((f.root/'build/ipad-mini-job-state.json').read_text())
   self.assertEqual(state['phases']['prepare']['status'],'completed')
   self.assertEqual(state['deadline_monotonic']-state['started_monotonic'],3000)
   record=json.loads((f.root/route.RECEIPT).read_text());self.assertEqual(record['project'],route.PROJECT)
   leases=[json.loads(line) for line in Path(str(log)+'.lease.jsonl').read_text().splitlines()]
   self.assertEqual(len({r['sha256'] for r in leases}),1)
   self.assertTrue(all(r['lease']['phase']=='host-prepare' for r in leases))
   self.assertNotIn('SHELL_ARGUMENT_ROUTING_PASS',result.stdout)
   self.assertTrue(base.preflight_contract(self.workflow))
  finally:owner.tearDown()


if __name__=='__main__':unittest.main()
