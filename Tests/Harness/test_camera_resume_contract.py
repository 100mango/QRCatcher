"""Source contracts for the observed async camera-resumption boundary, not UI proof."""
from pathlib import Path
import copy
import unittest

ROOT=Path(__file__).resolve().parents[2]
SOURCE=(ROOT/'QRCatcherUITests/QRCatcherUITests.m').read_text()
CASE=SOURCE.split('- (void)testProductionCameraAllowThenResetAndDeny {',1)[1].split('- (void)testProductionSceneLaunchWithoutCameraStub',1)[0]

def prompt_ready(application, nodes):
    """Independent context oracle for observed public nodes, not native execution."""
    if application!='com.apple.springboard': return False
    dialogs=[n for n in nodes if n['role']=='Alert' and n['label']=='Allow “QRCatcher” to access your camera?']
    if len(dialogs)!=1:return False
    buttons=[n for n in dialogs[0]['children'] if n['role']=='Button']
    allow=[n for n in buttons if n['label']=='Allow'];deny=[n for n in buttons if n['label']=='Don’t Allow']
    return (len(buttons)==2 and len(allow)==1 and len(deny)==1 and
            all(n['enabled'] and n['hittable'] for n in allow+deny))

def observed_prompt():
    return [{'role':'Alert','label':'Allow “QRCatcher” to access your camera?','children':[
        {'role':'Button','label':'Don’t Allow','enabled':True,'hittable':True},
        {'role':'Button','label':'Allow','enabled':True,'hittable':True}]}]

class CameraResumeContracts(unittest.TestCase):
    def test_same_exact_predicate_and_ten_second_bound_follow_actual_activation(self):
        self.assertIn('NSPredicate *unavailable = [NSPredicate predicateWithFormat:@"label CONTAINS %@", @"No camera is available"]',CASE)
        self.assertIn('[self waitForExpectationsWithTimeout:10 handler:nil]',CASE)
        resumed=CASE.split('[XCUIDevice.sharedDevice pressButton:XCUIDeviceButtonHome]; [self.app activate];',1)[1]
        self.assertIn('initWithPredicate:unavailable object:resumedStatus',resumed)
        self.assertIn('[XCTWaiter waitForExpectations:@[resumedUnavailable] timeout:10]',resumed)
        self.assertNotIn('sleep',resumed)

    def test_failure_stops_before_reset_or_deny_and_keeps_final_exact_state_assertion(self):
        resumed=CASE.split('XCUIElement *resumedStatus',1)[1]
        guard='if (resumedResult != XCTWaiterResultCompleted) return;'
        self.assertLess(resumed.index('XCTAssertEqual(resumedResult, XCTWaiterResultCompleted'),resumed.index(guard))
        self.assertLess(resumed.index(guard),resumed.index('[self.app resetAuthorizationStatusForResource:XCUIProtectedResourceCamera]'))
        self.assertIn('XCTAssertTrue([resumedLabel containsString:@"No camera is available"])',resumed)
        self.assertIn('NSProcessInfo.processInfo.systemUptime - resumeStarted',resumed)
        self.assertIn('PRODUCTION_CAMERA_RESUMED_WAIT outcome=%ld elapsed=%.3f',resumed)
        self.assertIn('PRODUCTION_CAMERA_RESUMED_STATE status=%@',resumed)
        self.assertLess(resumed.index(guard),resumed.index('resumedStatus.label'))
        self.assertNotIn('resumedStatus.exists',resumed)

    def test_actual_allow_reset_deny_and_default_case_limits_are_retained(self):
        self.assertEqual(CASE.count('resetAuthorizationStatusForResource:XCUIProtectedResourceCamera'),2)
        self.assertIn('QRRespondToObservedCameraPrompt(alert, @"Allow")',CASE)
        self.assertIn('QRRespondToObservedCameraPrompt(alert, @"Don’t Allow")',CASE)
        self.assertIn('XCTAssertTrue(handledAllow',CASE);self.assertIn('XCTAssertTrue(handledDeny)',CASE)
        self.assertIn('XCTAssertFalse(self.app.buttons[@"scan.settings"].exists)',CASE)
        self.assertIn('containsString:@"Camera access is off"',CASE)
        harness=(ROOT/'scripts/run_ios_platform_ui.sh').read_text()
        self.assertIn('-default-test-execution-time-allowance 180',harness)
        self.assertIn('-maximum-test-execution-time-allowance 240',harness)

    def test_passive_exact_prompt_gate_precedes_the_existing_single_allow_interaction(self):
        before=CASE.split('NSPredicate *unavailable',1)[0]
        gate=before.split('NSPredicate *cameraPromptReady',1)[1].split('NSTimeInterval promptStarted',1)[0]
        for token in ['cameraSystem.alerts matchingPredicate:', '@"Allow “QRCatcher” to access your camera?"',
                      'dialogs.count != 1', 'buttons.count == 2 && allow.count == 1 && deny.count == 1',
                      'allow.firstMatch.enabled && allow.firstMatch.hittable',
                      'deny.firstMatch.enabled && deny.firstMatch.hittable']:
            self.assertIn(token,gate)
        self.assertIn('initWithBundleIdentifier:@"com.apple.springboard"',before)
        self.assertNotIn(' tap]',gate); self.assertNotIn('sleep',gate)
        self.assertIn('[XCTWaiter waitForExpectations:@[cameraPrompt] timeout:10]',before)
        guard='if (promptResult != XCTWaiterResultCompleted) return;'
        self.assertLess(before.index(guard),before.index('[self.app tap]'))
        self.assertEqual(before.count('[self.app tap]'),1)
        self.assertLess(before.index('QRRespondToObservedCameraPrompt(alert, @"Allow")'),before.index('cameraPromptReady'))

    def test_prompt_context_rejects_wrong_application_role_title_and_duplicates(self):
        good=observed_prompt();self.assertTrue(prompt_ready('com.apple.springboard',good))
        self.assertFalse(prompt_ready('100mango.QRCatcher',good))
        self.assertFalse(prompt_ready('com.apple.springboard',[]))
        self.assertFalse(prompt_ready('com.apple.springboard',good+copy.deepcopy(good)))
        for key,value in [('role','Other'),('label','Allow “OtherApp” to access your camera?')]:
            wrong=copy.deepcopy(good);wrong[0][key]=value
            self.assertFalse(prompt_ready('com.apple.springboard',wrong))

    def test_prompt_controls_require_both_exact_unique_enabled_hittable_buttons(self):
        good=observed_prompt()
        for mode in ['missing','extra','duplicate','wrong-label','wrong-role','disabled','hidden']:
            wrong=copy.deepcopy(good);buttons=wrong[0]['children']
            if mode=='missing':buttons.pop()
            elif mode in ['extra','duplicate']:buttons.append(copy.deepcopy(buttons[0]))
            elif mode=='wrong-label':buttons[1]['label']='Continue'
            elif mode=='wrong-role':buttons[1]['role']='StaticText'
            elif mode=='disabled':buttons[1]['enabled']=False
            else:buttons[0]['hittable']=False
            with self.subTest(mode=mode):self.assertFalse(prompt_ready('com.apple.springboard',wrong))

if __name__=='__main__':unittest.main()
