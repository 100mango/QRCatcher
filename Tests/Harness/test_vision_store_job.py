"""Closed single Store job/source/clock tests; no Apple execution."""
import ast,contextlib,hashlib,io,json,os,runpy,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
import vision_store_job as job
from vision_case_contract import select_case,CASES,TARGETED_CASES,STORE_CASES

class StoreContract(unittest.TestCase):
 def environment(self):
  return {'GITHUB_JOB':'store','GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','GITHUB_REPOSITORY':'100mango/QRCatcher','GITHUB_REF':job.BRANCH,'EVIDENCE_SCOPE':'visionos_store','GITHUB_EVENT_NAME':'push','GITHUB_WORKFLOW_REF':'100mango/QRCatcher/'+job.WORKFLOW+'@'+job.BRANCH}
 def clock(self):
  e=self.environment();return dict(schema=1,repository=e['GITHUB_REPOSITORY'],ref=e['GITHUB_REF'],source=e['GITHUB_SHA'],workflow_sha=e['GITHUB_WORKFLOW_SHA'],run_id='123',attempt='1',job='store',scope='visionos_store',ceiling_seconds=2700,reserve_seconds=360,started_monotonic=100.)
 def test_clock_is_single_first_push_exact_workflow(self):
  self.assertEqual(job.inspect_clock(self.clock(),self.environment(),200.),('store','visionos_store',2600.))
  for key,value in [('GITHUB_JOB','photos'),('GITHUB_REF','refs/heads/main'),('GITHUB_REF','refs/heads/codex/vision-store-screenshot'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_EVENT_NAME','workflow_dispatch'),('GITHUB_WORKFLOW_REF','other'),('GITHUB_SHA','b'*40),('EVIDENCE_SCOPE','visionos_photos')]:
   e=self.environment();e[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):job.inspect_clock(self.clock(),e,200.)
 def test_phase_caps_preserve_original_clock_and_finalization_reserve(self):
  for phase,cap in job.CAPS['store'].items():
   reserve=360 if phase in job.BUSINESS['store'] else sum(job.CAPS['store'][p] for p in job.FINAL[job.FINAL.index(phase)+1:])+90
   self.assertEqual(job.phase_allowance('store',phase,cap+reserve),cap)
   with self.assertRaises(ValueError):job.phase_allowance('store',phase,cap+reserve-.1)
  for phase in ['hosted','archive','export','other']:
   with self.assertRaises(ValueError):job.phase_allowance('store',phase,2700)
 def test_business_end_still_admits_complete_finalization(self):
  reserve=job.JOBS['store'][2]
  self.assertGreaterEqual(reserve,sum(job.CAPS['store'][p] for p in job.FINAL)+90)
  self.assertEqual(job.phase_allowance('store','collect',reserve),job.CAPS['store']['collect'])
 def test_one_case_no_export_relaunch_or_mock_ui(self):
  case=select_case('visionos_store');self.assertEqual(STORE_CASES,(case,));self.assertEqual(len(CASES),4);self.assertEqual(len(TARGETED_CASES),1)
  self.assertEqual(case.frames,('vision-store-result',));self.assertTrue(case.photo_seed);self.assertFalse(case.hosted_tests);self.assertFalse(case.files_fixture);self.assertFalse(case.release_package)
  ui=(ROOT/'QRCatcherVisionUITests/QRCatcherVisionUITests.swift').read_text();method=ui.split('func testStoreScreenshotUnicodeResult() async {',1)[1].split('\n    }',1)[0]
  for expected in ['vision.photos','readyNativePhotoAsset','asset.tap()','vision.payload','QRCatcher 你好 🌈 123','vision.copy','Result copied','capture("vision-store-result")']:self.assertIn(expected,method)
  for forbidden in ['saveUsingSystemFileExporter','app.terminate','app.launch','vision.export','session.accept','launchEnvironment']:self.assertNotIn(forbidden,method)
  self.assertIn('captureScope != "visionos_store"',ui.split('override func tearDown()',1)[1].split('private func bindCaptureRunner',1)[0])
 def test_fixed_workflow_single_cohort_and_no_account_actions(self):
  w=json.loads((ROOT/job.WORKFLOW).read_text());self.assertEqual(w['on'],{'push':{'branches':['vision-store-screenshot']}});self.assertEqual(set(w['jobs']),{'store'});j=w['jobs']['store'];self.assertEqual(j['runs-on'],'xcode-27');self.assertEqual(j['timeout-minutes'],45);self.assertEqual(w['permissions'],{'contents':'read'});self.assertFalse(w['concurrency']['cancel-in-progress'])
  ids=[s.get('id') for s in j['steps']];self.assertTrue(all(p in ids for p in list(job.BUSINESS['store'])+list(job.FINAL)[:-1]));self.assertNotIn('hosted',ids)
  checkout=next(s for s in j['steps'] if s.get('uses','').startswith('actions/checkout@'));self.assertFalse(checkout['with']['persist-credentials']);self.assertEqual(checkout['with']['fetch-depth'],2)
  upload=next(s for s in j['steps'] if s.get('id')=='upload');self.assertEqual(upload['with']['retention-days'],1);self.assertIn("steps.validate.outputs.eligible == 'true'",upload['if'])
  raw=json.dumps(w)
  for forbidden in ['workflow_dispatch','apple-id','app-store-connect','fastlane','archive','hosted']:self.assertNotIn(forbidden,raw)
 def test_workflow_clock_literal_compiles_and_matches_driver(self):
  w=json.loads((ROOT/job.WORKFLOW).read_text());clock=w['jobs']['store']['steps'][0]['run'].split("PY_CLOCK'\n",1)[1].rsplit('\nPY_CLOCK',1)[0];ast.parse(clock)
  self.assertIn("scopes={'store':('visionos_store',2700,360)}",clock);self.assertIn("GITHUB_RUN_ATTEMPT']=='1'",clock);self.assertIn('QRCATCHER_VISION_STORE_CLOCK=',clock)
 def test_all_425_untouched_parent_inputs_match_bytes_modes(self):
  f=json.loads((ROOT/'scripts/vision_store_source_inputs.json').read_text());self.assertEqual(f['base_commit'],job.BASE);self.assertEqual(f['base_tree'],job.BASE_TREE);self.assertEqual(len(f['unchanged_inputs']),425)
  for row in f['unchanged_inputs']:
   p=ROOT/row['path'];raw=p.read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'],row['path']);self.assertEqual(len(raw),row['bytes']);self.assertEqual('100755' if p.stat().st_mode&0o111 else '100644',row['mode']);self.assertNotIn(row['path'],job.ALLOWED_CHANGED)
 def test_store_source_guard_positive_and_fail_closed_on_changed_product(self):
  fixture=json.loads((ROOT/'scripts/vision_store_source_inputs.json').read_text())
  paths=sorted({r['path'] for r in fixture['unchanged_inputs']}|job.ALLOWED_CHANGED)
  changed_paths=set(job.SUCCESSOR_PATHS)
  def runner(args,seconds):
   key=tuple(args[1:]); values={('rev-parse','HEAD'):'a'*40,('rev-list','--parents','-n','1','HEAD'):'a'*40+' '+job.PARENT,('diff','--name-only','HEAD','--'):'',('rev-parse',job.PARENT+'^{tree}'):job.PARENT_TREE,('diff','--name-only',job.PARENT,'HEAD','--'):'\n'.join(sorted(changed_paths)),('ls-files',):'\n'.join(paths),('rev-parse','HEAD^{tree}'):'b'*40}
   return 0,values[key],{'cleanup_confirmed':True}
  with patch.dict(os.environ,{'GITHUB_SHA':'a'*40}):
   result=job.source_snapshot(ROOT,runner);self.assertEqual(len(result['files']),442)
   changed_paths.add('scripts/vision_store_image.py')
   with self.assertRaisesRegex(ValueError,'source delta outside the Store runner correction'):job.source_snapshot(ROOT,runner)
   changed_paths.remove('scripts/vision_store_image.py')
   original=job.load_regular
   def changed(path,limit=512*1024):
    raw=original(path,limit)
    return raw+b'changed' if str(path).endswith('QRCatcherVision/VisionMainView.swift') else raw
   with patch.object(job,'load_regular',side_effect=changed),self.assertRaisesRegex(ValueError,'Unchanged product/build input differs'):
    job.source_snapshot(ROOT,runner)
 def test_no_legacy_capture_or_xcresult_retries_in_store_pipeline(self):
  run=(ROOT/'scripts/run_vision_store_case.py').read_text();self.assertIn("'scripts/capture_vision_store_checkpoint.py'",run);self.assertNotIn("'scripts/capture_vision_checkpoints.py'",run);self.assertIn("scope != 'visionos_store'",run)
  capture=(ROOT/'scripts/capture_vision_store_checkpoint.py').read_text();self.assertNotIn("'-Z'",capture);self.assertNotIn('unlink(',capture);self.assertNotIn('sips',capture)
  evidence=(ROOT/'scripts/vision_store_evidence.py').read_text();self.assertNotIn("'xcresulttool'",evidence);self.assertIn('allow_encode=False',(ROOT/'scripts/vision_store_job.py').read_text())
 def test_main_blocks_wrong_job_before_controller(self):
  with patch.dict(os.environ,{'GITHUB_JOB':'photos','EVIDENCE_SCOPE':'visionos_photos'},clear=True),patch.object(sys,'argv',['vision_store_job.py','prepare']),patch.object(job,'Job') as controller:
   with self.assertRaises(ValueError):job.main()
   controller.assert_not_called()
 def test_native_stage_routing_has_no_hosted_or_full_chain(self):
  raw=(ROOT/'scripts/vision_store_job.py').read_text();native=next(n for n in ast.walk(ast.parse(raw)) if isinstance(n,ast.FunctionDef) and n.name=='native');text=ast.get_source_segment(raw,native)
  for absent in ['VisionTestResults.xcresult','only-testing:QRCatcherVisionTests','export','archive']:self.assertNotIn(absent,text)
  self.assertIn("'Tests/Fixtures/unicode.png'",text);self.assertIn('run_vision_store_case.py',text)
  prepare=next(n for n in ast.walk(ast.parse(raw)) if isinstance(n,ast.FunctionDef) and n.name=='prepare');warmup=ast.get_source_segment(raw,prepare)
  self.assertEqual(warmup.count("'test_vision_store_*.py'"),2);self.assertNotIn("'test_vision_*.py'",warmup)
  self.assertIn("'-O'",warmup);self.assertIn('source_snapshot(self.root, self.run) == initial',warmup)

class StoreRouting(unittest.TestCase):
 def test_single_case_known_completion_and_all_nested_uncertainties(self):
  for mode in ['success','test-timeout','capture-timeout','capture-failed']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as folder:
    root=Path(folder).resolve();old=Path.cwd();calls=[];device='11111111-1111-4111-8111-111111111111'
    def execute(args,seconds):
     calls.append((args,seconds));code=0
     if mode=='test-timeout':code=124
     return code,'bounded original log',{'state':'timed_out' if code==124 else 'completed','cleanup_confirmed':True,'exit':code}
    class Capture:
     def wait(self,timeout):
      if mode=='capture-timeout':raise subprocess.TimeoutExpired('capture',timeout)
      return 1 if mode=='capture-failed' else 0
    env={'GITHUB_SHA':'a'*40,'EVIDENCE_SCOPE':'visionos_store','GITHUB_WORKSPACE':str(root),'GITHUB_ENV':str(root/'env'),'QRCATCHER_OWNED_PROCESS_BARRIER':str(root/'build/owned-process-cleanup.json')}
    try:
     os.chdir(root)
     with patch.dict(os.environ,env,clear=True),patch.object(sys,'argv',['run_vision_store_case.py',device,'visionos_store']),patch('watch_process.execute',side_effect=execute),patch('subprocess.Popen',return_value=Capture()) as launch,patch('owned_process_group.stop_group',return_value=True),contextlib.redirect_stdout(io.StringIO()):
      if mode=='success':runpy.run_path(str(ROOT/'scripts/run_vision_store_case.py'),run_name='__main__')
      else:
       with self.assertRaises(SystemExit):runpy.run_path(str(ROOT/'scripts/run_vision_store_case.py'),run_name='__main__')
      report=json.loads((root/'build/vision-runtime/ui-cases.json').read_text())
      launch.assert_called_once();self.assertIn('scripts/capture_vision_store_checkpoint.py',launch.call_args.args[0]);self.assertEqual(len(report['cases']),1)
      self.assertEqual(len(calls),1)
      command,cap=calls[0];self.assertEqual(command[0],'xcodebuild');self.assertEqual(cap,420)
      self.assertEqual([x for x in command if x.startswith('-only-testing:')],['-only-testing:QRCatcherVisionUITests/QRCatcherVisionUITests/testStoreScreenshotUnicodeResult'])
      self.assertNotIn('pre_case_app_termination',report['cases'][0])
      self.assertNotIn('simctl',command)
      if mode in ['test-timeout','capture-timeout']:self.assertTrue(report['cleanup_unconfirmed'])
      outer_code=0 if mode=='success' else 1
      outer={'state':'completed','exit':outer_code,'cleanup_confirmed':True}
      self.assertEqual(job.uncertain_operation('ui',outer_code,outer,report),mode in ['test-timeout','capture-timeout'])
    finally:os.chdir(old)


 def test_store_entry_rejects_every_non_store_scope_before_any_command(self):
  for scope in ['visionos_photos','visionos_files','visionos_chinese','visionos_largest','visionos_privacy']:
   with self.subTest(scope=scope),tempfile.TemporaryDirectory() as folder:
    old=Path.cwd()
    try:
     os.chdir(Path(folder).resolve())
     with patch.dict(os.environ,{},clear=True),patch.object(sys,'argv',['run_vision_store_case.py','11111111-1111-4111-8111-111111111111',scope]),patch('watch_process.execute') as execute,patch('subprocess.Popen') as capture:
      with self.assertRaisesRegex(ValueError,'only its exact single case'):runpy.run_path(str(ROOT/'scripts/run_vision_store_case.py'),run_name='__main__')
      execute.assert_not_called();capture.assert_not_called()
    finally:os.chdir(old)
 def test_existing_non_store_entry_preserves_termination_and_uncertainty_gate(self):
  for scope in ['visionos_photos','visionos_files','visionos_chinese','visionos_largest','visionos_privacy']:
   for mode in ['success','not-running','termination-timeout']:
    with self.subTest(scope=scope,mode=mode),tempfile.TemporaryDirectory() as folder:
     root=Path(folder).resolve();old=Path.cwd();calls=[];device='11111111-1111-4111-8111-111111111111'
     def execute(args,seconds):
      calls.append((args,seconds));code=124 if mode=='termination-timeout' else (3 if len(calls)==1 and mode=='not-running' else 0)
      return code,'bounded legacy log',{'state':'timed_out' if code==124 else 'completed','cleanup_confirmed':True,'exit':code}
     class Capture:
      def wait(self,timeout):return 0
     try:
      os.chdir(root)
      with patch.dict(os.environ,{'GITHUB_SHA':'a'*40,'EVIDENCE_SCOPE':scope},clear=True),patch.object(sys,'argv',['run_vision_ui_cases.py',device,scope]),patch('watch_process.execute',side_effect=execute),patch('run_native_size_case.run_case',return_value=(0,{'status':'passed'})) as largest,patch('subprocess.Popen',return_value=Capture()) as capture,patch('owned_process_group.stop_group',return_value=True),contextlib.redirect_stdout(io.StringIO()):
       if mode=='termination-timeout':
        with self.assertRaises(SystemExit):runpy.run_path(str(ROOT/'scripts/run_vision_ui_cases.py'),run_name='__main__')
       else:runpy.run_path(str(ROOT/'scripts/run_vision_ui_cases.py'),run_name='__main__')
       self.assertEqual(calls[0],(['xcrun','simctl','terminate',device,'100mango.QRCatcher'],30))
       capture.assert_called_once();self.assertIn('scripts/capture_vision_checkpoints.py',capture.call_args.args[0])
       report=json.loads((root/'build/vision-runtime/ui-cases.json').read_text());self.assertIn('pre_case_app_termination',report['cases'][0])
       if mode=='termination-timeout':
        self.assertEqual(len(calls),1);largest.assert_not_called();self.assertTrue(report['cleanup_unconfirmed'])
       elif scope=='visionos_largest':
        self.assertEqual(len(calls),1);largest.assert_called_once_with('vision',device)
       else:
        self.assertEqual(len(calls),2);self.assertEqual(calls[1][0][0],'xcodebuild');largest.assert_not_called()
     finally:os.chdir(old)

class SourceFinalHostReads(unittest.TestCase):
 def controller(self):
  value=job.Job.__new__(job.Job);value.phase='source_final';value.deadline=time.monotonic()+30
  value.row={'operations':[]};value.write=lambda:None
  return value
 def test_latched_device_barrier_allows_only_host_source_observation(self):
  value=self.controller();args=['git','rev-parse','HEAD']
  result=subprocess.CompletedProcess(args,0,b'a'*40+b'\n',b'')
  with patch.dict(os.environ,{'QRCATCHER_OWNED_CLEANUP_UNCONFIRMED':'true'}),patch.object(job,'capture',return_value=result) as read,patch.object(job,'execute') as native:
   code,text,receipt=value.run(args,10)
   self.assertEqual(code,0);self.assertEqual(text.strip(),'a'*40);self.assertTrue(receipt['host_read_only'])
   self.assertTrue(job.blocked());self.assertTrue(receipt['cleanup_confirmed'])
   read.assert_called_once_with(args,seconds=10,cap=256*1024,cleanup_grace=2)
   value.phase='ui'
   with self.assertRaisesRegex(ValueError,'forbids another native command'):value.run(['xcodebuild','test-without-building'],10)
   native.assert_not_called();self.assertTrue(job.blocked())
 def test_post_barrier_host_route_rejects_device_and_mutating_git_commands(self):
  with patch.dict(os.environ,{'QRCATCHER_OWNED_CLEANUP_UNCONFIRMED':'true'}),patch.object(job,'capture') as read,patch.object(job,'execute') as native:
   for args in [['xcrun','simctl','shutdown','DEVICE'],['xcodebuild','build'],['git','reset','--hard'],['git','-c','alias.read=!touch marker','read'],['git','status']]:
    with self.subTest(args=args),self.assertRaisesRegex(ValueError,'fixed read-only source Git'):self.controller().run(args,10)
   read.assert_not_called();native.assert_not_called();self.assertTrue(job.blocked())
 def test_host_read_failure_retains_barrier_and_cannot_become_success(self):
  for clean in (False,True):
   error=job.CaptureStopped('duration-limit',clean);error.stdout_prefix=b'partial';error.stderr_capture=b'failure'
   value=self.controller()
   with self.subTest(clean=clean),patch.dict(os.environ,{'QRCATCHER_OWNED_CLEANUP_UNCONFIRMED':'true'}),patch.object(job,'capture',side_effect=error),patch.object(job,'execute') as native:
    with self.assertRaisesRegex(ValueError,'Required command failed: git'):value.run(['git','ls-files'],10)
    receipt=value.row['operations'][-1];self.assertEqual(receipt['state'],'capture_stopped');self.assertEqual(receipt['cleanup_confirmed'],clean)
    self.assertEqual(receipt['exit'],126);native.assert_not_called();self.assertTrue(job.blocked())
 def test_host_source_read_reserves_both_cleanup_phases_without_new_clock(self):
  value=self.controller();value.deadline=time.monotonic()+13
  with patch.object(job,'capture') as read,self.assertRaisesRegex(ValueError,'Phase clock cannot admit'):value.run(['git','ls-files'],10)
  read.assert_not_called()

if __name__=='__main__':unittest.main()
