"""Targeted-only privacy routing and evidence boundaries; no native claims."""
import copy, os, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts'), str(Path(__file__).parent)]
from vision_case_contract import CASES, TARGETED_CASES, ALL_CASES, select_case
from export_vision_case_evidence import validate_frames
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
        self.assertFalse(any([case.hosted_tests, case.photo_seed, case.files_fixture, case.release_package])); self.assertEqual(case.seconds, 300)
        self.assertNotIn('visionos_privacy', allocation()['scope_limits_bytes'])
        self.assertEqual(contracts.check_workflow((ROOT/'.github/workflows/apple-platforms.yml').read_text()), 605)
        for invalid in ['', 'visionos_privacy,visionos_photos', 'visionos_privacy/../', 'privacy']:
            with self.assertRaises(ValueError): select_case(invalid)
    def test_chinese_policy_and_done_return_do_not_depend_on_photo_or_payload(self):
        body = UI.split('func testChineseOfflinePolicyEndingAndReturn() async {', 1)[1].split('\n    }', 1)[0]
        for value in ['privacy.tap()', 'privacy.offlineBody', 'privacy.offlineEnd', '100mango@gmail.com', '本地数据可通过相应应用或系统删除，权限可在系统设置中撤回。', 'revealPolicyEnding()', 'await capture("vision-privacy-end")', 'app.buttons["vision.privacyDone"].tap()', 'XCTAssertFalse(ending.exists)', 'await capture("vision-privacy-returned")']: self.assertIn(value, body)
        for forbidden in ['vision.photos', 'readyNativePhotoAsset', 'asset.tap()', 'loadTransferable', 'content_size', 'dynamicTypeSize']: self.assertNotIn(forbidden, body)
        self.assertIn('name.contains("testChineseOfflinePolicyEndingAndReturn")', UI)
        self.assertIn('name == "vision-chinese-policy" || name == "vision-privacy-end"', UI)
    def test_privacy_selects_one_exact_ui_command_without_retry_or_system_size(self):
        worker = routing.VisionRoutingTests(); worker.setUp()
        try:
            for kwargs in [{}, {'failed': True}, {'unknown_at': 1}, {'unknown_at': 2}]:
                os.environ.pop('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED', None); worker.exercise(select_case('visionos_privacy'), **kwargs)
        finally: worker.doCleanups()
    def test_privacy_exact_frames_and_source_identity_are_required(self):
        case = select_case('visionos_privacy')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); expected, bindings, rows = contracts.VisionFrameAndResultTests().fixture(case, root)
            validate_frames(case, expected, bindings, rows, root)
            for invalid in [rows[:1], rows + rows[:1], []]:
                with self.assertRaises(ValueError): validate_frames(case, expected, bindings, invalid, root)
            changed = copy.deepcopy(rows); changed[0]['source_commit'] = 'b' * 40
            with self.assertRaises(ValueError): validate_frames(case, expected, bindings, changed, root)
            changed = copy.deepcopy(rows); changed[0]['checkpoint'] = 'vision-chinese-policy'
            with self.assertRaises(ValueError): validate_frames(case, expected, bindings, changed, root)
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
if __name__ == '__main__': unittest.main()
