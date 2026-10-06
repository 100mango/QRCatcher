#!/usr/bin/env python3
"""Exact diagnostic32KiB ledger bounds and actual closed-script lifecycle doubles.
Fake Apple/Git commands provide synthetic results, not native/app/platform proof.
"""
from pathlib import Path
import hashlib,json,os,plistlib,subprocess,sys,time,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
import test_ipad_mini_setup as base
import ipad_mini_setup as mini
import diagnostic_mini_managed_route as route
import ios_original_release_route as ios_route


def diagnostic(f):
    # This fixture owns the old diagnostic profile even when discovery runs
    # inside the new iOS-first CI job. Do not inherit its compiler-double input.
    for key in ('IOS_FIRST_RELEASE_CANDIDATE_ONLY','SYNTHETIC_IOS_PRODUCTS',ios_route.INITIAL_HASH_KEY):
        os.environ.pop(key,None)
    for name in [route.CANONICAL,route.WORKFLOW]:
        path=f.root/name;path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():path.write_bytes((ROOT/name).read_bytes())
    os.environ.update(GITHUB_REF=route.REF,GITHUB_WORKFLOW_REF=route.WORKFLOW_REF,GITHUB_JOB='platform',
                      DIAGNOSTIC_ONLY='true',RUNNER_OS='macOS',RUNNER_ARCH='ARM64')
    value=json.loads(f.origin.read_text());value['caps']=mini.DIAGNOSTIC_CAPS;f.origin.write_text(json.dumps(value));f.origin.chmod(0o600)
    f.budget.path.unlink();f.budget=mini.Budget(f.clock)


STUB=r'''#!/usr/bin/env python3
import sys,os,json,plistlib,shutil
from pathlib import Path
name=Path(sys.argv[0]).name;args=sys.argv[1:]
with open(os.environ['APPLE_CALL_LOG'],'a') as f:f.write(json.dumps([name,args])+'\n')
if name=='git':
 if args[:2]==['rev-parse','HEAD']:print(os.environ['GITHUB_SHA'])
 elif args[:1]==['rev-parse']:print('b'*40)
elif name=='uname':print('arm64')
elif name=='sips':shutil.copyfile(args[args.index('--out')-1],args[args.index('--out')+1])
elif name=='xcodebuild':
 if args==['-version']:print('Xcode 27.0\nBuild version 27A266a')
 elif args[:1]==['build-for-testing']:
  if os.environ.get('IOS_FIRST_RELEASE_CANDIDATE_ONLY')=='true':
   shutil.copytree(os.environ['SYNTHETIC_IOS_PRODUCTS'],'build/iOS/Build/Products');print('Explicit iOS compiler double with public-layout synthetic package bytes');sys.exit(0)
  products=Path('build/iOS/Build/Products');parent=products/'Debug-iphonesimulator/QRCatcher.app';producer=products/'Debug-watchsimulator/QRCatcherWatch.app'
  parent.mkdir(parents=True);producer.mkdir(parents=True)
  base={'CFBundleShortVersionString':'1.1','CFBundleVersion':'2'}
  (parent/'Info.plist').write_bytes(plistlib.dumps({**base,'CFBundleIdentifier':'100mango.QRCatcher'}))
  info={**base,'CFBundleIdentifier':'100mango.QRCatcher.watchkitapp','CFBundleExecutable':'QRCatcherWatch','WKCompanionAppBundleIdentifier':'100mango.QRCatcher','WKApplication':True,'WKRunsIndependentlyOfCompanionApp':True,'MinimumOSVersion':'9.0','UIDeviceFamily':[4],'CFBundleIconName':'AppIcon','CFBundleSupportedPlatforms':['WatchSimulator']}
  (producer/'Info.plist').write_bytes(plistlib.dumps(info));(producer/'PrivacyInfo.xcprivacy').write_bytes(plistlib.dumps({'NSPrivacyAccessedAPITypes':[],'NSPrivacyCollectedDataTypes':[],'NSPrivacyTracking':False}))
  for n in ['QRCatcherWatch','Assets.car']:(producer/n).write_bytes(b'Explicit synthetic bundle marker; not an Apple executable')
  shutil.copyfile('ThirdParty/ZXingCpp/ThirdPartyNotices.txt',producer/'ThirdPartyNotices.txt');nested=parent/'Watch/QRCatcherWatch.app';nested.parent.mkdir();shutil.copytree(producer,nested)
  print('Explicit compiler double; no Apple compilation')
 elif args[:1]==['test-without-building']:
  result=Path(args[args.index('-resultBundlePath')+1]);result.mkdir();(result/'Info.plist').write_bytes(plistlib.dumps({'SyntheticResult':True}));print('Explicit full-row case double; no app/XCTest execution')
  if '-files.' in str(result) and os.environ.get('FILES_CASE_FAILURE')=='65':sys.exit(65)
 else:print('Explicit Xcode metadata double')
elif name=='xcrun':
 if args[:2]==['lipo','-archs']:print('arm64')
 elif args[:1]==['otool']:print('Load command 1\n cmd LC_BUILD_VERSION\n platform 9\n minos 9.0\n sdk 27.0')
 elif args==['simctl','list','-j']:print(json.dumps({'runtimes':[{'identifier':os.environ['RUNTIME'],'isAvailable':True}],'devicetypes':[{'name':'iPad mini (A17 Pro)','identifier':os.environ['TYPE']}],'devices':{os.environ['RUNTIME']:[]}}))
 elif args[:2]==['simctl','create']:print(os.environ['CREATED_DEVICE'])
 elif args==['simctl','list','devices','available','-j']:
  p=Path(os.environ['STATE_SEQUENCE']);states=json.loads(p.read_text());state=states.pop(0);p.write_text(json.dumps(states))
  print(json.dumps({'devices':{os.environ['RUNTIME']:[{'udid':os.environ['CREATED_DEVICE'],'name':'QRCatcher Mini '+os.environ['GITHUB_RUN_ID']+'-'+os.environ['GITHUB_RUN_ATTEMPT'],'deviceTypeIdentifier':os.environ['TYPE'],'isAvailable':True,'state':state}]}}))
 elif args[:2]==['simctl','bootstatus']:
  print('Monitoring boot status for QRCatcher Mini '+os.environ['GITHUB_RUN_ID']+'-'+os.environ['GITHUB_RUN_ATTEMPT']+' ('+os.environ['CREATED_DEVICE']+').\n[2026-10-06 01:04:59 +0000] Status=4, isTerminal=NO, Elapsed=00:47.\n\tWaiting on System App\n\n[2026-10-06 01:05:15 +0000] Status=4294967295, isTerminal=YES, Elapsed=01:03.\n\tFinished\n')
 elif args[:2]==['simctl','get_app_container']:print(os.environ['SYNTHETIC_APP' if args[-1]=='app' else 'SYNTHETIC_DATA'])
 elif args[:3]==['xcresulttool','get','test-results']:
  expected=2 if '-layout.' in args[-1] else 1
  failed=int('-files.' in args[-1] and os.environ.get('FILES_CASE_FAILURE')=='65')
  print(json.dumps({'totalTestCount':expected,'passedTests':expected-failed,'failedTests':failed,'skippedTests':0,'expectedFailures':0,'devicesAndConfigurations':[{'device':{'deviceId':os.environ['CREATED_DEVICE']}}],'runtimeWarnings':[],'result':'Failed' if failed else 'Passed','testFailures':[{'failureText':'Synthetic complete Files failure'}] if failed else []}))
 elif args[:3]==['xcresulttool','export','attachments']:
  out=Path(args[args.index('--output-path')+1]);out.mkdir(parents=True,exist_ok=True);(out/'manifest.json').write_text('[]')
 else:print('Explicit Apple command double; no service execution')
else:print('Explicit Apple metadata double')
'''


def full_lifecycle(long_ids=False,files_failure=False,ios_first=False):
    """Actual phase/row/export/validation/gate/summary/final scripts, all Apple doubled."""
    owner=base.MiniSetupTests();owner.setUp()
    try:
        owner.real_fixture();f=owner.f
        if ios_first:
            os.environ.update(GITHUB_REF=ios_route.REF,GITHUB_WORKFLOW_REF=ios_route.WORKFLOW_REF,GITHUB_JOB='platform',
                              IOS_FIRST_RELEASE_CANDIDATE_ONLY='true',RUNNER_OS='macOS',RUNNER_ARCH='ARM64')
            value=json.loads(f.origin.read_text());value['caps']=mini.IOS_FIRST_CAPS;f.origin.write_text(json.dumps(value));f.origin.chmod(0o600)
            f.budget.path.unlink();f.budget=mini.Budget(f.clock)
            from test_ios_only_release_package import IOSOnlyPackageTests
            package=IOSOnlyPackageTests();package.setUp();package.hosted(ui_target=True)
        else:diagnostic(f)
        if long_ids:
            value=json.loads(f.origin.read_text());value.update(run_id='9'*20,run_attempt='8'*20)
            os.environ.update(GITHUB_RUN_ID=value['run_id'],GITHUB_RUN_ATTEMPT=value['run_attempt'])
            origin=f.temp/('qrcatcher-mini-'+value['run_id']+'-'+value['run_attempt']+'.json');origin.write_text(json.dumps(value));origin.chmod(0o600)
            os.environ['QRCATCHER_MINI_JOB_ORIGIN']=str(origin);f.budget=mini.Budget(time.monotonic)
        binary=f.root/'bin';binary.mkdir();log=f.root/'fake-apple-calls.log';seq=f.root/'states.json';seq.write_text(json.dumps(['Shutdown']*(4 if ios_first else 3)))
        app=f.root/'synthetic-app';app.mkdir();data=f.root/'synthetic-data';data.mkdir()
        (app/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'100mango.QRCatcher','UIFileSharingEnabled':True,'LSSupportsOpeningDocumentsInPlace':True}))
        for name in ['git','sw_vers','xcodebuild','uname','sips','xcrun','plutil']:(binary/name).write_text(STUB);(binary/name).chmod(0o755)
        env={**os.environ,'PATH':str(binary)+os.pathsep+os.environ['PATH'],'APPLE_CALL_LOG':str(log),'STATE_SEQUENCE':str(seq),
             'SYNTHETIC_APP':str(app),'SYNTHETIC_DATA':str(data),'RUNTIME':base.RUNTIME,'TYPE':base.TYPE,'CREATED_DEVICE':base.DEVICE,'FILES_CASE_FAILURE':'65' if files_failure else '0'}
        if ios_first:env['SYNTHETIC_IOS_PRODUCTS']=str(package.xctestrun.parent)
        if not __debug__:env['PYTHONOPTIMIZE']='1'
        else:env.pop('PYTHONOPTIMIZE',None)
        sizes=[];outputs=[];operations=[]
        def run(args,timeout=30,expected_exit=0):
            result=subprocess.run(args,cwd=f.root,env=env,capture_output=True,text=True,timeout=timeout,start_new_session=True)
            outputs.append({'command':args,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
            if result.returncode!=expected_exit:raise AssertionError(result.stdout+result.stderr)
            if (f.root/'env').exists():
                for line in (f.root/'env').read_text().splitlines():
                    key,value=line.split('=',1);env[key]=value
            ledger=f.root/'build/ipad-mini-job-state.json';sizes.append({'command':args,'bytes':ledger.stat().st_size});return ledger.read_bytes()
        controller=[sys.executable,'scripts/ipad_mini_setup.py']
        for phase in ['prepare','build']:run(controller+['phase',phase])
        run(controller+['configure']);run(['bash','scripts/run_ios_platform_ui.sh',base.DEVICE,'MiniUIResults.xcresult','QRCatcherPadUITests'],expected_exit=65 if files_failure else 0)
        completed_row=json.loads((f.root/'build/ipad-mini-job-state.json').read_text());row_bytes=(f.root/'build/ipad-mini-job-state.json').stat().st_size
        if json.loads(seq.read_text()):raise AssertionError('State sequence not consumed')
        if f.setup()['unexecuted']!=[] or f.setup()['real_photo_case_exit']!=0:raise AssertionError('Full fake case sequence incomplete')
        if f.setup()['real_files_case_exit']!=(65 if files_failure else 0):raise AssertionError('Files outcome lost before actual Photos attempt')
        if (data/'Documents/QRCatcher-Test-Imports/SyntheticQR.png').read_bytes()!=(f.root/'Tests/Fixtures/unicode.png').read_bytes():raise AssertionError('Original fixture changed')
        handoffs=list(completed_row['phases']['mini']['state_handoffs'].values())
        recovery_count=3 if ios_first else 2
        if [item['boot_attempts'] for item in handoffs]!=[1]*recovery_count:raise AssertionError('Once-only Shutdown recoveries missing')
        if [item['observations'][0]['state'] for item in handoffs]!=['Shutdown']*recovery_count or [len(item['observations']) for item in handoffs]!=[1]*recovery_count:raise AssertionError('Fresh Shutdown prechecks required without readbacks')
        if any(item['state']!='bootstatus_completion_observation_only' or item['readiness_basis']!='exact_owned_uuid_bootstatus_completion' for item in handoffs):raise AssertionError('Exact observed bootstatus readiness missing')
        calls=[json.loads(line) for line in log.read_text().splitlines()]
        if sum(name=='xcrun' and args==['simctl','list','devices','available','-j'] for name,args in calls)!=recovery_count+1:raise AssertionError('Repeated state readback')
        for action in ['boot','bootstatus']:
            if sum(name=='xcrun' and args[:2]==['simctl',action] for name,args in calls)!=recovery_count:raise AssertionError('Once-only owned '+action+' commands missing')
        run(controller+['phase','export']);exported=(f.root/'build/ios-platform-evidence/ipad-mini-job-state.json').read_bytes()
        mini.read_regular(f.root/'build/ios-platform-evidence/ipad-mini-job-state.json',32768)
        run(controller+['phase','validate']);validation=json.loads((f.root/'build/platform-evidence-budget.json').read_text())
        run(controller+['upload-enter']);run(controller+['upload-exit'])  # Local gate calls only; no action/upload executes.
        run(controller+['phase','summary']);last=run(controller+['phase','final']);state=json.loads(last)
        reloaded=subprocess.run(controller+['summaries'],cwd=f.root,env=env,capture_output=True,text=True,timeout=10)
        if reloaded.returncode:raise AssertionError(reloaded.stdout+reloaded.stderr)
        for phase in mini.ORDER:
            status=state['phases'][phase]['status'];wanted='platform_action_returned' if phase=='upload' else 'completed_failed' if phase=='mini' and files_failure else 'completed'
            if status!=wanted:raise AssertionError((phase,status))
        if state['full_job_accepted'] or state['post_checkout']['status']!='pending_platform_post_action':raise AssertionError('False post/job acceptance')
        if any((f.root/'build'/name).exists() for name in ['ipad-mini-inflight.json','ipad-mini-host-inflight.json','fixture-query-inflight.json','owned-process-cleanup.json']):raise AssertionError('Unresolved owned child marker')
        if not (f.root/'build/ipad-mini-row-dispatched.json').exists():raise AssertionError('Permanent row marker lost')
        if max(item['bytes'] for item in sizes)>32768 or len(last)<=16384 or len(exported)<=16384:raise AssertionError('Expected complete large ledger not retained')
        if validation['scope_limit_bytes']!=2_000_000 or validation['combined_limit_bytes']!=20_000_000:raise AssertionError('Evidence caps changed')
        return {'classification':'actual complete checked-script lifecycle with explicit Apple/Git/bundle/case doubles; no native or platform action',
                'ios_first_profile':ios_first,'long_identifiers':long_ids,'files_case_exit':65 if files_failure else 0,'photos_case_exit':f.setup()['real_photo_case_exit'],'row_ledger_bytes':row_bytes,'exported_ledger_bytes':len(exported),'final_ledger_bytes':len(last),'maximum_measured_bytes':max(item['bytes'] for item in sizes),
                'ledger_limit':32768,'headroom_bytes':32768-len(last),'sizes':sizes,'outputs':outputs,'ledger':state,'ledger_raw':last,'exported_raw':exported,
                'validated_evidence_bytes':validation['current']['bytes'],'scope_limit_bytes':validation['scope_limit_bytes'],
                'retained_operation_records':sum(len(item['operations']) for item in state['phases'].values()),'full_job_accepted':False,'native_execution':False,'actual_upload_executed':False,'platform_post_observed':False}
    finally:
        if ios_first and 'package' in locals():package.doCleanups()
        owner.tearDown()


class MiniLedgerTests(unittest.TestCase):
    def setUp(self):self.f=base.Fixture()
    def tearDown(self):self.f.close()
    def test_canonical_producer_reader_remain16k(self):
        self.assertEqual(self.f.budget.ledger_limit,16384);self.assertEqual(mini.job_ledger_limit(),16384)
        self.f.budget.state['synthetic_padding']='x'*17000
        with self.assertRaises(ValueError):self.f.budget.persist()
    def test_canonical_constructor_rejects_over16k(self):
        state=self.f.budget.state;state['synthetic_padding']='x'*17000;self.f.budget.path.write_text(json.dumps(state));self.f.budget.path.chmod(0o600)
        with self.assertRaises(ValueError):mini.Budget(self.f.clock)
    def test_exact_diagnostic32k_roundtrip_preserves_all_records(self):
        diagnostic(self.f);self.assertEqual(self.f.budget.ledger_limit,32768);self.assertEqual(mini.job_ledger_limit(),32768)
        self.f.budget.state['synthetic_padding']='x'*20000;self.f.budget.persist();self.assertGreater(self.f.budget.path.stat().st_size,16384)
        reloaded=mini.Budget(self.f.clock);self.assertEqual(reloaded.state,self.f.budget.state)
    def test_diagnostic_producer_rejects_over32k_without_replacing_last_good_state(self):
        diagnostic(self.f);self.f.budget.persist();before=self.f.budget.path.read_bytes();self.f.budget.state['synthetic_padding']='x'*32768
        with self.assertRaises(ValueError):self.f.budget.persist()
        self.assertEqual(self.f.budget.path.read_bytes(),before)
    def test_diagnostic_constructor_rejects_over32k(self):
        diagnostic(self.f);self.f.budget.state['synthetic_padding']='x'*32768;self.f.budget.path.write_text(json.dumps(self.f.budget.state));self.f.budget.path.chmod(0o600)
        with self.assertRaises(ValueError):mini.Budget(self.f.clock)
    def test_forged_diagnostic_identity_does_not_expand_ledger(self):
        diagnostic(self.f);os.environ['GITHUB_WORKFLOW_REF']='wrong-workflow'
        with self.assertRaises(ValueError):mini.job_ledger_limit()
    def test_generic_read_default_remains16k(self):
        self.assertEqual(mini.read_regular.__defaults__,(16384,))
    def exporter_oversize(self,diagnostic_route,padding):
        owner=base.MiniSetupTests();owner.f=self.f;owner.install_source()
        if diagnostic_route:diagnostic(self.f)
        self.f.budget.state['synthetic_padding']='x'*padding
        self.f.budget.path.write_text(json.dumps(self.f.budget.state));self.f.budget.path.chmod(0o600)
        binary=self.f.root/'bin';binary.mkdir();git=binary/'git'
        git.write_text("#!/usr/bin/env python3\nimport os,sys\nprint(os.environ['GITHUB_SHA'] if sys.argv[-1]=='HEAD' else 'b'*40)\n");git.chmod(0o755)
        env={**os.environ,'PATH':str(binary)+os.pathsep+os.environ['PATH']}
        if not __debug__:env['PYTHONOPTIMIZE']='1'
        result=subprocess.run([sys.executable,'scripts/export_ios_platform_screenshots.py'],cwd=self.f.root,env=env,capture_output=True,text=True,timeout=10)
        self.assertNotEqual(result.returncode,0,result.stdout+result.stderr);self.assertIn('Invalid evidence file',result.stderr)
        self.assertFalse((self.f.root/'build/ios-platform-evidence/ipad-mini-job-state.json').exists())
    def test_actual_canonical_exporter_refuses_over16k(self):self.exporter_oversize(False,17000)
    def test_actual_diagnostic_exporter_refuses_over32k(self):self.exporter_oversize(True,32768)
    def test_actual_complete_two_shutdown_lifecycle_retains_large_ledger(self):
        result=full_lifecycle();self.assertGreater(result['final_ledger_bytes'],16384);self.assertLess(result['final_ledger_bytes'],32768)
        self.assertEqual(result['retained_operation_records'],23);self.assertFalse(result['full_job_accepted'])
        print('COMPLETE_LEDGER_LIFECYCLE '+json.dumps({k:v for k,v in result.items() if k not in ['ledger','ledger_raw','exported_raw','outputs','sizes']}),flush=True)
    def test_actual_failed_files65_lifecycle_still_attempts_photos_with_two_shutdown_handoffs(self):
        result=full_lifecycle(files_failure=True)
        self.assertEqual(result['files_case_exit'],65);self.assertEqual(result['photos_case_exit'],0)
        self.assertEqual(result['ledger']['phases']['mini']['status'],'completed_failed')
        self.assertEqual(result['retained_operation_records'],23);self.assertFalse(result['full_job_accepted'])
        self.assertGreater(result['final_ledger_bytes'],16384);self.assertLess(result['final_ledger_bytes'],32768)
        print('COMPLETE_LEDGER_LIFECYCLE '+json.dumps({k:v for k,v in result.items() if k not in ['ledger','ledger_raw','exported_raw','outputs','sizes']}),flush=True)
    def test_actual_complete_long_identifier_lifecycle_retains_large_ledger(self):
        result=full_lifecycle(True);self.assertGreater(result['final_ledger_bytes'],16384);self.assertLess(result['final_ledger_bytes'],32768)
        self.assertFalse(result['actual_upload_executed']);self.assertFalse(result['platform_post_observed'])
        print('COMPLETE_LEDGER_LIFECYCLE '+json.dumps({k:v for k,v in result.items() if k not in ['ledger','ledger_raw','exported_raw','outputs','sizes']}),flush=True)
    def test_actual_diagnostic_lifecycle_owns_profile_under_poisoned_outer_ios_ci(self):
        poison={'GITHUB_REF':ios_route.REF,'GITHUB_WORKFLOW_REF':ios_route.WORKFLOW_REF,
                'GITHUB_JOB':'preflight','EVIDENCE_SCOPE':'','IOS_FIRST_RELEASE_CANDIDATE_ONLY':'true',
                'SYNTHETIC_IOS_PRODUCTS':'/outer/foreign-ios-products',ios_route.INITIAL_HASH_KEY:'c'*64}
        with patch.dict(os.environ,poison):
            result=full_lifecycle()
            self.assertEqual({key:os.environ.get(key) for key in poison},poison)
        state=result['ledger'];row=state['phases']['mini']
        self.assertFalse(result['ios_first_profile'])
        self.assertEqual(state['deadline_monotonic'],state['started_monotonic']+3000)
        self.assertEqual(row['deadline'],row['started']+1920)
        self.assertEqual(state['phases']['build']['deadline'],state['phases']['build']['started']+480)
        self.assertEqual([op['cap'] for op in state['phases']['build']['operations']],[435,20])
        self.assertEqual([item['caps'] for item in row['state_handoffs'].values()],
                         [{'precheck':30,'boot':30,'bootstatus':90}]*2)
        self.assertNotIn('row_admissions',row);self.assertEqual(result['retained_operation_records'],23)
        self.assertEqual(result['files_case_exit'],0);self.assertEqual(result['photos_case_exit'],0)
        self.assertFalse(result['full_job_accepted']);self.assertLess(result['maximum_measured_bytes'],32768)
        print('POISONED_OUTER_IOS_DIAGNOSTIC_LIFECYCLE '+json.dumps({k:v for k,v in result.items() if k not in ['ledger','ledger_raw','exported_raw','outputs','sizes']}),flush=True)
    def test_actual_ios_first_three_shutdown_lifecycle_preserves_schedule_and_caps(self):
        result=full_lifecycle(ios_first=True);state=result['ledger'];row=state['phases']['mini']
        self.assertEqual(state['deadline_monotonic'],state['started_monotonic']+3000)
        self.assertEqual(row['deadline'],row['started']+2220)
        self.assertEqual(state['phases']['build']['deadline'],state['phases']['build']['started']+180)
        self.assertEqual([op['cap'] for op in state['phases']['build']['operations']],[135,20])
        self.assertEqual([item['caps'] for item in row['state_handoffs'].values()],
                         [{'precheck':30,'boot':30,'bootstatus':210},{'precheck':30,'boot':30,'bootstatus':90},{'precheck':30,'boot':30,'bootstatus':90}])
        self.assertEqual(sum(op['cap'] for op in row['operations'])+60,2090)
        self.assertEqual(len(row['operations'])+2,21)
        self.assertEqual([row['row_admissions'][stage]['required_seconds'] for stage in ('configure','first_bootstrap','layout')],[2152,2026,1750])
        self.assertEqual(row['row_admissions']['layout']['completed_first_bootstrap_debit_seconds'],276)
        self.assertEqual(row['row_admissions']['layout']['skipped_first_boot_pair_seconds'],0)
        self.assertLess(result['maximum_measured_bytes'],32768)
        print('IOS_FIRST_COMPLETE_LEDGER_LIFECYCLE '+json.dumps({k:v for k,v in result.items() if k not in ['ledger','ledger_raw','exported_raw','outputs','sizes']}),flush=True)
    def test_actual_ios_first_failed_files_long_identifier_lifecycle_continues_photos(self):
        result=full_lifecycle(long_ids=True,files_failure=True,ios_first=True)
        self.assertEqual(result['files_case_exit'],65);self.assertEqual(result['photos_case_exit'],0)
        self.assertEqual(result['ledger']['phases']['mini']['status'],'completed_failed')
        self.assertLess(result['maximum_measured_bytes'],32768)
        print('IOS_FIRST_COMPLETE_LEDGER_LIFECYCLE '+json.dumps({k:v for k,v in result.items() if k not in ['ledger','ledger_raw','exported_raw','outputs','sizes']}),flush=True)

if __name__=='__main__':unittest.main()
