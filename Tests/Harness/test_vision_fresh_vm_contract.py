"""Portable workflow, selection and evidence-boundary negative fixtures."""
import contextlib, copy, hashlib, io, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from vision_case_contract import CASES, SCOPES, case_identity, require_identity, select_case
from validate_evidence_budget import allocation, inspect
from export_vision_case_evidence import validate_frames, validate_host_failure, validate_result


def check_workflow(text):
    # The existing workflow has one closed scalar scope matrix. This intentionally
    # rejects a second matrix, dynamic include, cache or downloaded VM state.
    def need(condition,message):
        if not condition:raise ValueError(message)
    need(text.count('      matrix:\n        scope:\n')==1,'Expected one closed fresh-job matrix')
    scopes=text.split('      matrix:\n        scope:\n',1)[1].split("'on':",1)[0]
    actual=[line.strip()[2:] for line in scopes.splitlines() if line.strip().startswith('- ')]
    expected=['watchos','macos','watchos_40','watchos_49']+[case.scope for case in CASES]+['tvos','iphone_pro','iphone_se3','ipad_pro','ipad_mini']
    need(actual==expected,'One distinct matrix VM per existing Vision case required')
    for required in ['  group: qrcatcher-apple-platforms\n','  cancel-in-progress: false\n','      fail-fast: false\n','      max-parallel: 1\n','    timeout-minutes: 45\n','    timeout-minutes: 20\n']:
        need(text.splitlines().count(required.rstrip('\n'))==1,'Concurrency/job cap changed: '+required.strip())
    need(text.count('    runs-on: xcode-27\n')==2,'Standard runner changed')
    for forbidden in ['actions/cache','actions/download-artifact','self-hosted','workflow_dispatch','continue-on-error','retry']:
        need(forbidden not in text,'Unexpected reuse/retry/control: '+forbidden)
    steps={block.splitlines()[0]:block for block in text.split('    - name: ')[1:]}
    hosted=steps['Execute native Vision hosted decode and persistence']
    release=steps['Verify unsigned native Vision device Release package']
    need("matrix.scope == 'visionos_photos'" in hosted,'Hosted tests must run once on Photos')
    need("matrix.scope == 'visionos_files'" in release,'Release must run once on Files')
    install=steps['Install the exact built Vision app before any fixtures']
    need('run_bounded.py 90 xcrun simctl install "$VISION_SIMULATOR_ID" build/VisionTests/Build/Products/Debug-xrsimulator/QRCatcherVision.app' in install,'Exact bounded install required')
    seed=steps['Seed the Vision QR photo only for the selected Photos case']
    need("matrix.scope == 'visionos_files'" not in seed and all("matrix.scope == '"+scope+"'" in seed for scope in ['visionos_photos','visionos_chinese','visionos_largest']),'Photo seed scope changed')
    need('run_bounded.py 150 xcrun simctl addmedia' in seed and 'stage_owned_import_fixture.py' not in seed,'Photo seed cap or independence changed')
    stage=steps['Stage only the selected Vision Files fixture']
    need("matrix.scope == 'visionos_files'" in stage and 'simctl addmedia' not in stage,'Files must not require Photos')
    for value in [seed,stage,hosted]:need("steps.vision_app_install.outcome == 'success'" in value,'Fixture/hosted must follow successful install')
    need(text.index('Install the exact built Vision app')<text.index('Seed the Vision QR photo')<text.index('Execute exactly one existing Vision'),'Install/fixture/case order changed')
    runner=steps['Execute exactly one existing Vision UI case on this fresh VM']
    need('run_vision_ui_cases.py "$VISION_SIMULATOR_ID" "$EVIDENCE_SCOPE"' in runner,'Closed selector not forwarded')
    need("steps.vision_files_stage.outcome == 'success'" in runner and "steps.vision_photo_seed.outcome == 'success'" in runner,'Required fixture gate missing')
    for value in [install,seed,stage,runner,hosted,release]:
        need("env.QRCATCHER_OWNED_CLEANUP_UNCONFIRMED != 'true'" in value and 'python3 scripts/owned_process_barrier.py --check' in value,'Owned cleanup barrier missing')
    need(text.count('retention-days: 1')==2,'One-day retention changed')
    need('name: qrcatcher-${{ matrix.scope }}-evidence' in text,'Case-specific artifact identity missing')
    need('export_vision_case_evidence.py "$EVIDENCE_SCOPE"' in text,'Case-bound exporter missing')
    need('path: build/ios-platform-evidence' in text and 'path: *.xcresult' not in text,'Raw result upload forbidden')
    return 20+len(actual)*45


class FreshVMWorkflowTests(unittest.TestCase):
    def test_four_rows_preserve_serial_standard_runner_caps(self):
        self.assertEqual(check_workflow((ROOT/'.github/workflows/apple-platforms.yml').read_text()),605)
    def test_workflow_scope_concurrency_reuse_seed_and_install_mutations_are_rejected(self):
        original=(ROOT/'.github/workflows/apple-platforms.yml').read_text()
        mutations=[('        - visionos_files\n',''),('max-parallel: 1','max-parallel: 2'),('timeout-minutes: 45','timeout-minutes: 46'),('cancel-in-progress: false','cancel-in-progress: true'),('runs-on: xcode-27','runs-on: self-hosted'),('run_bounded.py 90 xcrun simctl install','run_bounded.py 100 xcrun simctl install'),('run_bounded.py 150 xcrun simctl addmedia','run_bounded.py 200 xcrun simctl addmedia'),('run_vision_ui_cases.py "$VISION_SIMULATOR_ID" "$EVIDENCE_SCOPE"','run_vision_ui_cases.py "$VISION_SIMULATOR_ID"'),('retention-days: 1','retention-days: 2')]
        for old,new in mutations:
            with self.subTest(old=old),self.assertRaises(ValueError):check_workflow(original.replace(old,new))
    def test_closed_selector_rejects_combined_default_unknown_and_path_input(self):
        self.assertEqual(len(CASES),4);self.assertEqual(len({c.result for c in CASES}),4)
        self.assertEqual(sum(c.hosted_tests for c in CASES),1);self.assertEqual(sum(c.release_package for c in CASES),1)
        for value in [None,'','visionos','visionos_photos,visionos_files','VISIONOS_FILES','../visionos_files']:
            with self.subTest(value=value),self.assertRaises(ValueError):select_case(value)
    def test_identity_rejects_changed_case_result_source_or_device(self):
        good=case_identity(CASES[0],'a'*40,'11111111-1111-4111-8111-111111111111')
        for key in good:
            invalid=good.copy();invalid[key]='wrong'
            with self.subTest(key=key),self.assertRaises(ValueError):require_identity(invalid,good)
        for source in ['a'*39,'A'*40,'head','a'*40+'\n']:
            with self.assertRaises(ValueError):case_identity(CASES[0],source,good['device'])


class EvidenceAllocationTests(unittest.TestCase):
    def test_exact_allocation_and_vision_caps(self):
        value=allocation();self.assertEqual(sum(value['scope_limits_bytes'].values()),19_800_000)
        self.assertEqual(value['whole_run_limit_bytes'],20_000_000)
        self.assertEqual(sum(c.evidence_bytes for c in CASES),2_800_000)
    def test_allocation_unknown_bool_increased_and_missing_scope_fail_under_optimization(self):
        good=allocation()
        values=[]
        for key in ['visionos_photos','visionos_files','visionos_chinese','visionos_largest']:
            bad=copy.deepcopy(good);bad['scope_limits_bytes'][key]+=1;values.append(bad)
        bad=copy.deepcopy(good);bad['scope_limits_bytes']['visionos']=bad['scope_limits_bytes'].pop('visionos_files');values.append(bad)
        bad=copy.deepcopy(good);bad['scope_limits_bytes']['visionos_files']=True;values.append(bad)
        bad=copy.deepcopy(good);bad['whole_run_limit_bytes']=20_000_001;values.append(bad)
        for value in values:
            with patch.object(Path,'read_text',return_value=json.dumps(value)),self.assertRaises(ValueError):allocation()
    def test_each_scope_exact_boundary_passes_one_byte_over_fails(self):
        for case in CASES:
            with self.subTest(scope=case.scope),tempfile.TemporaryDirectory() as folder:
                path=Path(folder).resolve();first=min(800*1024,case.evidence_bytes)
                (path/'frame.jpg').write_bytes(b'x'*first)
                if first<case.evidence_bytes:(path/'tail.log').write_bytes(b'x'*(case.evidence_bytes-first))
                self.assertEqual(inspect(path,limit=case.evidence_bytes)['bytes'],case.evidence_bytes)
                (path/'one.log').write_bytes(b'x')
                with self.assertRaises(ValueError):inspect(path,limit=case.evidence_bytes)
    def test_raw_results_symlink_and_oversized_files_are_rejected(self):
        for mode in ['raw','symlink','large']:
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder).resolve()
                if mode=='raw':(path/'raw.xcresult').write_bytes(b'x')
                elif mode=='large':(path/'big.jpg').write_bytes(b'x'*(800*1024+1))
                else:(path/'link.jpg').symlink_to(path/'missing')
                with self.assertRaises(ValueError):inspect(path)


class VisionFrameAndResultTests(unittest.TestCase):
    def fixture(self,case,path):
        expected=case_identity(case,'a'*40,'11111111-1111-4111-8111-111111111111')
        binding=dict(expected,success=True,lease='22222222-2222-4222-8222-222222222222',runner='100mango.QRCatcherVisionUITests.xctrunner',pid=123,exports=case.hosted_tests)
        rows=[]
        for name in case.frames:
            data=b'\xff\xd8'+name.encode();(path/(name+'.jpg')).write_bytes(data)
            row=dict(binding,checkpoint=name,file=name+'.jpg',pixels_retained=True,screenshot_exit=0,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            if name.startswith('vision-exported-'):
                kind='png' if name=='vision-exported-qr' else 'json';exported=b'export-png' if kind=='png' else b'{"format":"QRCatcher.history"}';(path/('actual-export.'+kind)).write_bytes(exported)
                row['actual_export_readback']={'test_store':'33333333-3333-4333-8333-333333333333','type':kind,'bytes':len(exported),'sha256':hashlib.sha256(exported).hexdigest()}
            rows.append(row)
        return expected,[binding],rows
    def test_each_exact_frame_set_and_export_receipts_qualify(self):
        for case in CASES:
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder).resolve();expected,bindings,rows=self.fixture(case,path)
                self.assertEqual(len(validate_frames(case,expected,bindings,rows,path)),len(case.frames))
    def test_missing_duplicate_wrong_case_result_device_source_lease_hash_and_export_fail(self):
        modes=['missing','duplicate','scope','case','result','device','source_commit','lease','hash','export','host-substitution']
        for mode in modes:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as folder:
                path=Path(folder).resolve();case=CASES[0];expected,bindings,rows=self.fixture(case,path)
                if mode=='missing':rows.pop()
                elif mode=='duplicate':rows.append(rows[0])
                elif mode=='hash':rows[0]['sha256']='f'*64
                elif mode=='export':(path/'actual-export.png').write_bytes(b'wrong')
                elif mode=='host-substitution':rows[0]['checkpoint']='vision-host-failure'
                else:rows[0][mode]='wrong'
                with self.assertRaises(ValueError):validate_frames(case,expected,bindings,rows,path)
    def test_success_result_requires_one_exact_case_and_device_no_skips(self):
        case=CASES[0];device='11111111-1111-4111-8111-111111111111'
        summary={'totalTestCount':1,'passedTests':1,'failedTests':0,'skippedTests':0,'expectedFailures':0,'result':'Passed','devicesAndConfigurations':[{'device':{'deviceId':device,'platform':'visionOS Simulator'}}]}
        tests={'testNodes':[{'nodeType':'Test Case','name':case.name+'()','nodeIdentifier':'QRCatcherVisionUITests/'+case.name+'()','nodeIdentifierURL':'test://com.apple.xcode/QRCatcher/QRCatcherVisionUITests/QRCatcherVisionUITests/'+case.name,'result':'Passed'}]}
        validate_result(summary,tests,case,device)
        for mode in ['case','target','two','device','skipped','bool']:
            wrong_summary=copy.deepcopy(summary);wrong_tests=copy.deepcopy(tests)
            if mode=='case':wrong_tests['testNodes'][0]['nodeIdentifier']='QRCatcherVisionUITests/testOther()'
            elif mode=='target':wrong_tests['testNodes'][0]['nodeIdentifierURL']=wrong_tests['testNodes'][0]['nodeIdentifierURL'].replace('/QRCatcherVisionUITests/', '/OtherTarget/', 1)
            elif mode=='two':wrong_tests['testNodes']*=2
            elif mode=='device':wrong_summary['devicesAndConfigurations'][0]['device']['deviceId']='wrong'
            elif mode=='skipped':wrong_summary['skippedTests']=1
            else:wrong_summary['totalTestCount']=True
            with self.subTest(mode=mode),self.assertRaises(ValueError):validate_result(wrong_summary,wrong_tests,case,device)


class VisionExporterIntegrationTests(unittest.TestCase):
    def exercise(self,case,mode=None):
        from export_vision_case_evidence import export, ICON
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();runtime=root/'build/vision-runtime';runtime.mkdir(parents=True)
            expected,bindings,rows=VisionFrameAndResultTests().fixture(case,runtime)
            (runtime/'runner-bindings.json').write_text(json.dumps(bindings))
            if mode=='aggregate-oversized':
                for row in rows:
                    data=b'\xff\xd8'+b'x'*250000;(runtime/row['file']).write_bytes(data)
                    row.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            (runtime/'checkpoint-captures.json').write_text(json.dumps(rows))
            report=dict(expected,cases=[dict(expected,state='finished',exit=0)],capture_cleanup_confirmed=True,capture_process_exit=0)
            if mode=='case-failed':report['cases'][0]['exit']=124
            if mode=='wrong-case':report['cases'][0]['case']='testOther'
            if mode=='missing-frame':(runtime/(case.frames[0]+'.jpg')).unlink()
            if mode=='oversized-frame':(runtime/(case.frames[0]+'.jpg')).write_bytes(b'x'*(800*1024+1))
            if mode=='failure-substitute':
                rows[0]['checkpoint']='vision-host-failure';(runtime/'checkpoint-captures.json').write_text(json.dumps(rows))
            (runtime/'ui-cases.json').write_text(json.dumps(report))
            if mode in ['host-failure','host-wrong-lease']:
                data=b'\xff\xd8host-failure';(runtime/'vision-host-failure.jpg').write_bytes(data)
                failure=dict(bindings[0],success=False,diagnostic_only=True,pixels_retained=True,capture_success=True,file='vision-host-failure.jpg',bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
                if mode=='host-wrong-lease':failure['lease']='wrong'
                (runtime/'host-failure-capture.json').write_text(json.dumps(failure))
            if case.scope=='visionos_largest':(runtime/'system-content-size.json').write_text(json.dumps({'status':'largest_ui_passed','restore_verified':mode!='restore-failed'}))
            results=[case.result]+(['VisionTestResults.xcresult'] if case.hosted_tests else [])
            for result in results:(root/result).mkdir();(root/result/'Info.plist').write_bytes(b'fixture')
            if mode=='cross-result':(root/'VisionUIResults.xcresult').mkdir()
            if case.release_package:
                (root/ICON).parent.mkdir(parents=True);(root/ICON).write_bytes(b'\x89PNG'+b'i'*373983)
                package=root/'build/native-release-evidence/vision-release.json';package.parent.mkdir();package.write_text('{}')
                fixture=root/'build/import-fixture/fixture.json';fixture.parent.mkdir();fixture.write_text('{}')
            def command(arguments,**kwargs):
                hosted=arguments[-1]=='VisionTestResults.xcresult';count=11 if hosted else 1
                if arguments[4]=='summary':
                    data={'totalTestCount':count,'passedTests':count,'failedTests':0,'skippedTests':0,'expectedFailures':0,'result':'Passed','devicesAndConfigurations':[{'device':{'deviceId':expected['device'],'platform':'visionOS Simulator'}}]}
                elif arguments[4]=='tests':data={'testNodes':[{'nodeType':'Test Case','name':case.name+'()','nodeIdentifier':'QRCatcherVisionUITests/'+case.name+'()','nodeIdentifierURL':'test://com.apple.xcode/QRCatcher/QRCatcherVisionUITests/QRCatcherVisionUITests/'+case.name,'result':'Passed'}]}
                else:raise ValueError('Unexpected command')
                return subprocess.CompletedProcess(arguments,0,json.dumps(data),'')
            old=Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ,{'EVIDENCE_SCOPE':case.scope,'GITHUB_SHA':'a'*40,'VISION_SIMULATOR_ID':expected['device']}),patch('subprocess.check_output',side_effect=['a'*40,'b'*40]),patch('subprocess.run',side_effect=command),contextlib.redirect_stdout(io.StringIO()):
                    if mode:
                        with self.assertRaises(ValueError if mode=='aggregate-oversized' else SystemExit):export(case.scope)
                    else:export(case.scope)
                out=root/'build/ios-platform-evidence';summary=json.loads((out/'manifest.json').read_text())
                self.assertEqual(summary['qualified'],not bool(mode))
                self.assertEqual((out/'vision-retained-icon-source.png').exists(),case.release_package)
                if mode=='aggregate-oversized':self.assertGreater(sum(p.stat().st_size for p in out.iterdir()),case.evidence_bytes)
                else:self.assertLessEqual(sum(p.stat().st_size for p in out.iterdir()),case.evidence_bytes)
                if mode in ['host-failure','host-wrong-lease']:self.assertEqual((out/'vision-host-failure.jpg').exists(),mode=='host-failure')
                if mode=='case-failed':self.assertTrue((out/('vision-'+case.frames[0]+'.jpg')).exists(),'Valid partial native frames survive a later XCTest failure')
                return summary
            finally:os.chdir(old)
    def test_every_closed_case_exports_its_exact_set_with_icon_only_on_files(self):
        for case in CASES:
            with self.subTest(scope=case.scope):self.exercise(case)
    def test_failed_incomplete_or_substituted_evidence_retains_red_manifest(self):
        for mode in ['case-failed','wrong-case','missing-frame','oversized-frame','failure-substitute','cross-result','host-failure','host-wrong-lease','aggregate-oversized']:
            with self.subTest(mode=mode):self.exercise(CASES[0],mode)
        self.exercise(CASES[3],'restore-failed')

if __name__=='__main__':unittest.main()
