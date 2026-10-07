"""Targeted-only privacy routing and evidence boundaries; no native claims."""
import contextlib, copy, io, json, os, plistlib, runpy, sys, tempfile, unittest, uuid
from unittest.mock import patch
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts'), str(Path(__file__).parent)]
from vision_case_contract import CASES, TARGETED_CASES, ALL_CASES, select_case
from export_vision_case_evidence import validate_frames, validate_result
import vision_runner_binding as lease
import vision_failure_diagnostic as failure
from validate_evidence_budget import allocation, inspect
import test_vision_ui_cases as routing
import test_vision_fresh_vm_contract as contracts
import test_vision_command_fence as fences
UI = (ROOT/'QRCatcherVisionUITests/QRCatcherVisionUITests.swift').read_text()
class TargetedPrivacyTests(unittest.TestCase):
    def test_new_case_is_explicit_and_does_not_expand_canonical_matrix(self):
        case = select_case('visionos_privacy')
        self.assertEqual(len(CASES), 4); self.assertEqual(TARGETED_CASES, (case,)); self.assertNotIn(case, CASES)
        self.assertEqual(case.name, 'testChineseOfflinePolicyEndingAndReturn'); self.assertEqual(case.result, 'VisionPrivacyUIResults.xcresult')
        self.assertFalse(any([case.hosted_tests, case.photo_seed, case.files_fixture, case.release_package])); self.assertEqual(case.seconds, 300); self.assertEqual(case.frames, ()); self.assertTrue(case.functional_only)
        self.assertNotIn('visionos_privacy', allocation()['scope_limits_bytes'])
        self.assertEqual(contracts.check_workflow((ROOT/'.github/workflows/apple-platforms.yml').read_text()), 605)
        for invalid in ['', 'visionos_privacy,visionos_photos', 'visionos_privacy/../', 'privacy']:
            with self.assertRaises(ValueError): select_case(invalid)
    def test_chinese_policy_and_done_return_do_not_depend_on_photo_or_payload(self):
        body = UI.split('func testChineseOfflinePolicyEndingAndReturn() async {', 1)[1].split('\n    }', 1)[0]
        for value in ['privacy.tap()', 'privacy.offlineBody', 'privacy.offlineEnd', '100mango@gmail.com', '本地数据可通过相应应用或系统删除，权限可在系统设置中撤回。', 'revealPolicyEnding()', 'let done = app.buttons["vision.privacyDone"]', 'XCTAssertTrue(done.isEnabled)', 'XCTAssertTrue(done.isHittable)', 'done.tap()', 'XCTAssertFalse(ending.exists)', 'XCTAssertTrue(privacy.isHittable)', 'XCTAssertFalse(app.scrollViews["vision.privacyScroll"].exists)', 'XCTAssertTrue(app.buttons["vision.import"].isHittable)']: self.assertIn(value, body)
        for forbidden in ['vision.photos', 'readyNativePhotoAsset', 'asset.tap()', 'loadTransferable', 'content_size', 'dynamicTypeSize', 'capture(', 'performAccessibilityAudit']: self.assertNotIn(forbidden, body)
        self.assertIn('name.contains("testChineseOfflinePolicyEndingAndReturn")', UI)
        self.assertIn('name == "vision-chinese-policy" || name == "vision-privacy-end"', UI)
    def test_privacy_selects_one_exact_ui_command_without_retry_or_system_size(self):
        worker = routing.VisionRoutingTests(); worker.setUp()
        try:
            for kwargs in [{}, {'failed': True}, {'unknown_at': 1}, {'unknown_at': 2}]:
                os.environ.pop('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED', None); worker.exercise(select_case('visionos_privacy'), **kwargs)
        finally: worker.doCleanups()
    def test_functional_privacy_still_requires_current_runner_and_rejects_pixel_receipts(self):
        case = select_case('visionos_privacy')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); expected, bindings, rows = contracts.VisionFrameAndResultTests().fixture(case, root)
            self.assertEqual(validate_frames(case, expected, bindings, rows, root), [])
            for invalid in [[], bindings + bindings, [dict(bindings[0], success=False)], [dict(bindings[0], source_commit='b'*40)]]:
                with self.assertRaises(ValueError): validate_frames(case, expected, invalid, rows, root)
            for name in ['vision-privacy-end', 'vision-privacy-returned', 'vision-failure']:
                with self.assertRaises(ValueError): validate_frames(case, expected, bindings, [dict(bindings[0], checkpoint=name)], root)
    def test_complete_chinese_copy_is_exact_and_viewport_remains_geometric(self):
        body = UI.split('func testChineseOfflinePolicyEndingAndReturn() async {', 1)[1].split('\n    }', 1)[0]
        policy = (ROOT/'Shared/Services/QRPrivacyText.swift').read_text().split('static let simplifiedChinese = "',1)[1].split('"',1)[0]
        prefix, ending = policy.split('本地数据可',1)
        self.assertIn('XCTAssertEqual(body.label, "' + prefix + '")', body)
        self.assertIn('XCTAssertEqual(ending.label, "本地数据可' + ending + '")', body)
        geometry = UI.split('private func revealPolicyEnding()',1)[1].split('private func saveUsingSystemFileExporter',1)[0]
        self.assertIn('end.isHittable && scroll.frame.contains(lastLine)', geometry)
        self.assertIn('scroll.swipeUp()', geometry)
        self.assertIn('captureScope != "visionos_privacy"', UI.split('override func tearDown()',1)[1].split('private func bindCaptureRunner',1)[0])
    def test_functional_export_requires_exact_passed_case_and_never_claims_pixels(self):
        case = select_case('visionos_privacy'); worker = contracts.VisionExporterIntegrationTests()
        summary = worker.exercise(case)
        self.assertEqual(summary['qualification'], 'functional-only')
        self.assertFalse(summary['new_privacy_pixels']); self.assertFalse(summary['store_screenshots'])
        self.assertEqual(summary['required_frames'], [])
        for mode in ['wrong-case','cross-result','pending-fence','global-uncertainty']:
            with self.subTest(mode=mode): worker.exercise(case, mode)
        result = summary['results'][case.result]
        for mode in ['failed','skipped','wrong-device','wrong-method','two-tests']:
            value = copy.deepcopy(result['summary']); tests = copy.deepcopy(result['tests'])
            if mode == 'failed': value.update(result='Failed',passedTests=0,failedTests=1)
            elif mode == 'skipped': value.update(passedTests=0,skippedTests=1)
            elif mode == 'wrong-device': value['devicesAndConfigurations'][0]['device']['deviceId']='wrong'
            elif mode == 'wrong-method': tests['testNodes'][0]['name']='testOther()'
            else: tests['testNodes'] *= 2
            with self.subTest(mode=mode), self.assertRaises(ValueError): validate_result(value,tests,case,summary['device'])
    def test_privacy_scope_uses_same_exclusive_shell_fence(self):
        worker = fences.VisionFenceTests(); worker.setUp()
        try:
            worker.env['EVIDENCE_SCOPE'] = 'visionos_privacy'; result = worker.shell()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr); self.assertEqual(len(worker.calls()), 1); self.assertFalse(worker.latch.exists())
        finally: worker.doCleanups()
    def test_privacy_evidence_limit_and_existing_result_exclusion_are_preserved(self):
        case = select_case('visionos_privacy')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); (root/'frame.jpg').write_bytes(b'x' * case.evidence_bytes)
            self.assertEqual(inspect(root, limit=case.evidence_bytes)['bytes'], 550000); (root/'more.log').write_bytes(b'x')
            with self.assertRaises(ValueError): inspect(root, limit=case.evidence_bytes)
        self.assertIn('VisionPrivacyUIResults.xcresult', (ROOT/'scripts/run_vision_ui_cases.py').read_text())
        self.assertIn('for other in ALL_CASES:', (ROOT/'scripts/export_vision_case_evidence.py').read_text())
class FunctionalPrivacyCollectorTests(unittest.TestCase):
    def exercise(self, mode):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve(); home=root/'home'; work=root/'work'; work.mkdir()
            device,nonce,container,request=[str(uuid.uuid4()).upper() for _ in range(4)]
            runner=home/'Library/Developer/CoreSimulator/Devices'/device/'data/Containers/Data/Application'/container
            (runner/'tmp').mkdir(parents=True)
            case=select_case('visionos_privacy')
            (runner/'tmp'/('QRCatcher-runner-'+nonce+'.json')).write_text(json.dumps({'id':nonce,'runner':lease.RUNNER,'pid':123,'exports':False,'case':case.name}))
            info=work/'build/VisionTests/Build/Products/Debug-xrsimulator/QRCatcherVisionUITests-Runner.app/Info.plist'
            info.parent.mkdir(parents=True); info.write_bytes(plistlib.dumps({'CFBundleIdentifier':lease.RUNNER}))
            out=work/'build/vision-runtime'; out.mkdir(); (out/'ui-completed.marker').touch()
            log=('QRCATCHER_VISION_RUNNER_READY:'+nonce+'\n') if mode!='missing-binding' else ''
            if mode=='observed-failure': log+='error: -[QRCatcherVisionUITests.QRCatcherVisionUITests '+case.name+'] : failed - fixture failure\n'
            if mode=='checkpoint-request': log+='QRCATCHER_VISION_CAPTURE_REQUEST:'+request+'\n'
            (work/'run.log').write_text(log)
            calls=[]
            def lookup(args,seconds,**kwargs):
                calls.append(args)
                return 0,str(runner),{'state':'completed','exit':0,'cleanup_confirmed':True}
            env={'GITHUB_SHA':'a'*40,'EVIDENCE_SCOPE':case.scope,'GITHUB_WORKSPACE':str(work),'QRCATCHER_OWNED_PROCESS_BARRIER':str(work/'build/owned-process-cleanup.json')}
            old=Path.cwd(); code=0
            try:
                os.chdir(work)
                with patch.dict(os.environ,env,clear=True), patch.object(Path,'home',return_value=home), patch.object(lease,'execute',side_effect=lookup), patch('subprocess.run',side_effect=AssertionError('No screenshot or conversion permitted')), patch.object(failure.FailureDiagnostic,'observe',side_effect=AssertionError('No optional failure screenshot permitted')), patch.object(sys,'argv',['capture_vision_checkpoints.py',device,'run.log',case.scope]), contextlib.redirect_stdout(io.StringIO()):
                    try: runpy.run_path(str(ROOT/'scripts/capture_vision_checkpoints.py'),run_name='__main__')
                    except SystemExit as error: code=error.code
            finally: os.chdir(old)
            if mode in ['normal','observed-failure']:
                self.assertEqual(code,0); self.assertEqual(json.loads((out/'checkpoint-captures.json').read_text()),[])
                self.assertEqual(len(calls),1); self.assertEqual(calls[0][:3],['xcrun','simctl','get_app_container'])
                binding=json.loads((out/'runner-bindings.json').read_text()); self.assertTrue(binding[0]['success'])
                ack=json.loads((runner/'tmp'/('QRCatcher-runner-'+nonce+'.ack')).read_text()); self.assertEqual(ack['scope'],case.scope)
            else: self.assertNotEqual(code,0)
            self.assertFalse(list(out.glob('*.jpg'))); self.assertFalse(list(out.glob('*.png')))
            self.assertFalse((out/'host-failure-capture.json').exists())
    def test_binding_only_on_success_and_XCTest_failure_with_no_pixel_side_effect(self):
        # A known XCTest failure is qualified by the outer actual result, never
        # by this binding-only helper's clean exit.
        for mode in ['normal','observed-failure','missing-binding','checkpoint-request']:
            with self.subTest(mode=mode): self.exercise(mode)

if __name__ == '__main__': unittest.main()
