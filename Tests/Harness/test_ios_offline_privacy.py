"""Closed offline privacy source/native contracts; no Apple runtime proof.

Default policy reads local approved copy. The exact legacy observer hashes
remain historical: only the independently pinned new privacy assertion block
is removed for those historical inputs, never arbitrary test behavior.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
NATIVE_REFERENCE = {'QRCatcherTests/QRCatcherTests.m': {'all_case_names': ['testQRRoundTrip', 'testSharedCodecMatchesOriginalUIImageOracle', 'testPreviewRotationMappingAndSavedSelectionPreserveHistory', 'testSmallestHistoricalPhoneGeometryWithLargestText', 'testEmptyQR', 'testNonQRCodeImageDoesNotDecode', 'testSafeWebsiteClassification', 'testHistoryDeduplicatesAndDeletes', 'testLegacyStoreReopensWithoutLosingHistory', 'testUnreadableStoreIsNotDeleted', 'testCorruptHistoryShowsErrorAndStillAllowsCopy', 'testPrivacyHTTPFailuresAndWebProcessTerminationOfferRetry'], 'unchanged_method_sha256': {'testQRRoundTrip': '3fa24bf93bab6fe0061dd252f4f60080df94d12821c5659e0e1ffced5af4ca28', 'testSharedCodecMatchesOriginalUIImageOracle': '1c3829452b18626c95bae2783c01ffafc179002dc305e7be86603270746c54fc', 'testPreviewRotationMappingAndSavedSelectionPreserveHistory': 'de20fdbb3152a7fa199c65d3ba0a57dacb17f8ff38649f7cbb3341dadb77e58c', 'testSmallestHistoricalPhoneGeometryWithLargestText': '33f4ef52811a2a6b1b2c741523ac2cacb5fd6fd511e8454ad873083b5ce21997', 'testEmptyQR': '6b3136aa284a897ccce9079dabaa64b722be830bafad74798231f63bd5fa3546', 'testNonQRCodeImageDoesNotDecode': 'a1887e28c850a7f34d828f3462820a68051412e733137bb922a8a0c22ada1324', 'testSafeWebsiteClassification': 'ed9b9d2d200ec22e9f7f1ae4a5c7a6c90c5d10064a591d98fe9597dbfdd298da', 'testHistoryDeduplicatesAndDeletes': '5cea84fc2c4a2a2da1b071783c015186261fa3ab9d296e5207f7ad652ac3aca8', 'testLegacyStoreReopensWithoutLosingHistory': 'e57e6d9c1471978fc9f31f79e08ec54dd0a8aaa6aeb68c51c59006343866f260', 'testUnreadableStoreIsNotDeleted': '5c5360301d8989a1b4643e5595e692c91edf459b43e82c762ae37fcce8756cf2', 'testCorruptHistoryShowsErrorAndStillAllowsCopy': 'f6a181f20bd49ade5f9bb346543dab07af31ba2ce47c9c87eedb544f967268bb'}}, 'QRCatcherUITests/QRCatcherUITests.m': {'all_case_names': ['testProductionCameraAllowThenResetAndDeny', 'testProductionSceneLaunchWithoutCameraStub', 'testDeniedCameraAndEmptyHistory', 'testScannedTextPersistsAcrossRelaunchAndBackground', 'testUnreadableResultOffersRetryWithoutSaving', 'testWebsiteRequiresExplicitOpenAndCanScanAgain', 'testLargeTextLayoutKeepsControlsReachable', 'testAccessibilityOfResultAndHistory'], 'unchanged_method_sha256': {'testProductionCameraAllowThenResetAndDeny': 'c0945a6a3408d68e857ba2b575280be3a2ce997993af3d70d9a72366bf26d248', 'testProductionSceneLaunchWithoutCameraStub': 'ff12d14cf4a11dfaa4bd9b5085e0611a4a08d88cf15dd826d2221b23744aa3c7', 'testScannedTextPersistsAcrossRelaunchAndBackground': '119af95f22fd26f550cd001bd42d68d73470324e81e6055a13729c0f6c881c8e', 'testUnreadableResultOffersRetryWithoutSaving': '3c7581ab2ae350e792d6aae7442ad4ecdc9f8bc85127c55308ec28fb507d3048', 'testWebsiteRequiresExplicitOpenAndCanScanAgain': '273ff0287e6582595a91d14db8a4b68dbf7cbeebfe8f3beddb1d85bf4cb84ea6', 'testAccessibilityOfResultAndHistory': '15ebffb7fb426d093008604a3d711552d16b4ea10e2f9a7ec0460c02cbe91d44'}}, 'QRCatcherUITests/QRCatcherPadUITests.m': {'all_case_names': ['testSplitSelectionRotationAndAnchoredShare', 'testRealPhotoImportReplacesSelectionAndPreservesBothRecords', 'testLargeTextImportCancellationAndPrivacyReturn'], 'unchanged_method_sha256': {'testSplitSelectionRotationAndAnchoredShare': '0ccd8c9377397335c5331523e92e417a1ac2c66ee35ac3eec97139c494f91066', 'testRealPhotoImportReplacesSelectionAndPreservesBothRecords': '0342f1c950a5a0f780905fe189cecfd054b6968fa42211dfac792bc9d556ceb8'}}}
PAD_BLOCK_SHA256 = '4457c0e5d303b118c9fe2f18e993e7027169f1ff646b0183a355399fd38357b5'
PAD_BASE_SHA256 = 'ec3d7211c2b844af6d8320d081847990b960fe5f4af02a83db88bd552c562edf'

PAD_START = '    XCUIElement *policyBody = self.app.staticTexts[@"privacy.body"];'
PAD_END = '    [self.app.navigationBars.buttons[@"privacy.close"] tap];'


def restore_pad_for_historical_observer(text):
    text = restore_pad_share_observation(text)
    if PAD_START not in text:
        return text
    if text.count(PAD_START) != 1:
        raise ValueError('Ambiguous offline privacy assertion block')
    start = text.index(PAD_START)
    end = text.index(PAD_END, start)
    block = text[start:end]
    if hashlib.sha256(block.encode()).hexdigest() != PAD_BLOCK_SHA256:
        raise ValueError('Changed admitted offline privacy assertion block')
    return text[:start] + text[end:]


def test_methods(text):
    result = {}
    for match in re.finditer(r'^- \(void\)(test\w+) \{', text, re.M):
        following = re.search(r'^- \([^\n]+\)|^@end', text[match.end():], re.M)
        end = match.end() + following.start() if following else len(text)
        result[match[1]] = text[match.start():end]
    return result


def method(text, selector):
    match = re.search(r'^- \([^\n]+\)' + re.escape(selector) + r'[^\n]*\{', text, re.M)
    if not match:
        raise ValueError('Missing owned method: ' + selector)
    following = re.search(r'^- \([^\n]+\)|^@end', text[match.end():], re.M)
    end = match.end() + following.start() if following else len(text)
    return text[match.start():end]


def default_contract(source):
    for token in ('WKWebView', 'loadRequest:', 'NSURLSession', 'NSURLConnection', 'SFSafariViewController'):
        if token in source:
            raise ValueError('Unexpected in-app network surface: ' + token)
    loaded = method(source, 'viewDidLoad')
    if 'openExternalURL:' in loaded or '[self openPolicyInBrowser]' in loaded:
        raise ValueError('Default privacy presentation opens a website')
    opened = method(source, 'openPolicyInBrowser')
    for required in ('if (self.closing || self.opening) return;', 'self.opening = YES;',
                     '[self openExternalURL:URL completion:',
                     'https://100mango.github.io/app-privacy/',
                     'if (!strongSelf || strongSelf.closing) return;'):
        if required not in opened:
            raise ValueError('Missing closed explicit opening gate')
    actual = method(source, 'openExternalURL:')
    if actual.count('[UIApplication.sharedApplication openURL:URL options:@{} completionHandler:completion]') != 1:
        raise ValueError('Owned explicit action must use the existing public browser API')
    if source.count('https://100mango.github.io/app-privacy/') != 1:
        raise ValueError('Fixed policy URL must have a unique action-owned use')


def browser_observation_contract(source):
    case = test_methods(source)['testDeniedCameraAndEmptyHistory']
    observer = 'XCUIApplication *browser = [[XCUIApplication alloc] initWithBundleIdentifier:@"com.apple.mobilesafari"];'
    action = '[self.app.buttons[@"privacy.externalPolicy"] tap];'
    if case.count(observer) != 1 or case.count(action) != 1 or case.index(observer) >= case.index(action):
        raise ValueError('Safari observer must precede the unique real policy tap')
    if re.search(r'\[browser\s+(?:launch|activate|terminate|open)\b', case):
        raise ValueError('Browser activity cannot manufacture the handoff')
    for getter in ('externalPolicy.exists', 'externalPolicy.enabled', 'externalPolicy.hittable'):
        if case.count(getter) != 1 or case.index(getter) >= case.index(action):
            raise ValueError('The actual external policy action must be ready before tapping')
    start = case.index('NSPredicate *browserForeground =')
    end = case.index('    }];', start)
    predicate = case[start:end]
    getter = 'browser.state'
    if predicate.count(getter) != 1:
        raise ValueError('Each poll must read only the same public Safari state once')
    before, after = predicate.split(getter)
    if 'if (!timely()) return NO;' not in before or 'if (!timely()) return NO;' not in after:
        raise ValueError('Missing shared deadline around the returned public state')
    required = ('XCUIApplicationState browserState = browser.state;',
                'if (statePairs.count < 12)', 'samplesOmitted = YES;',
                'return browserState == XCUIApplicationStateRunningForeground;')
    if any(token not in predicate for token in required):
        raise ValueError('Missing Safari foreground observation and bounded state diagnostics')
    observation = case[case.index('    NSTimeInterval handoffStarted ='):case.index('    [self.app activate];')]
    if any(token in observation for token in ('self.app.state', 'browser.windows', 'window.',
                                              'debugDescription', 'waitForExistence', 'matchingIdentifier:',
                                              'matchingPredicate:', '[browser activate]', '[browser launch]')):
        raise ValueError('Manual review cannot add Safari AX selectors or another app state requirement')
    if case.count('XCUIScreen.mainScreen.screenshot.image') != 1:
        raise ValueError('Manual browser review requires exactly one native full-screen acquisition')
    capture_start = case.index('    BOOL captureRetained = NO;')
    capture_end = case.index('    NSDictionary *stateTrace =', capture_start)
    capture = case[capture_start:capture_end]
    for token in ('if (handoff == XCTWaiterResultCompleted && timely())',
                  'manualReceipt[@"capture_attempts"] = @1;',
                  'UIImage *image = XCUIScreen.mainScreen.screenshot.image;',
                  'if (timely() && image.CGImage)',
                  'size_t width = CGImageGetWidth(image.CGImage);',
                  'size_t height = CGImageGetHeight(image.CGImage);',
                  'NSData *JPEG = UIImageJPEGRepresentation(image, 0.55);',
                  'if (timely() && QRPrivacyManualCaptureRetainable(width, height, JPEG.length))',
                  'manualReceipt[@"native_width"] = @(width);',
                  'manualReceipt[@"native_height"] = @(height);',
                  'manualReceipt[@"source_bytes"] = @(JPEG.length);',
                  '[XCTAttachment attachmentWithData:JPEG uniformTypeIdentifier:@"public.jpeg"]',
                  'attachment.name = @"privacy-browser-manual-review";',
                  'attachment.lifetime = XCTAttachmentLifetimeKeepAlways;',
                  '[self addAttachment:attachment];', 'captureRetained = timely();',
                  '@catch (NSException *exception)',
                  'if (!captureRetained) self.privacyBrowserCaptureUnknown = YES;',
                  'if (!timely()) handoff = XCTWaiterResultTimedOut;'):
        if token not in capture:
            raise ValueError('Missing native unscaled bounded capture or fail-closed deadline clause')
    for token in ('NSTimeInterval handoffStarted = NSProcessInfo.processInfo.systemUptime;',
                  'QRPrivacyObservationTimely(handoffStarted, NSProcessInfo.processInfo.systemUptime)',
                  'if (self.privacyBrowserObservationLate) return NO;',
                  'if (!valid) self.privacyBrowserObservationLate = YES;',
                  'XCTWaiterResult handoff = [XCTWaiter waitForExpectations:@[openedOutside] timeout:10];',
                  'XCTAssertEqual(handoff, XCTWaiterResultCompleted,',
                  'XCTAssertTrue(captureRetained,',
                  'if (handoff != XCTWaiterResultCompleted || !captureRetained) return;',
                  'stateTraceData.length <= 2048', 'manualData.length <= 1024',
                  '@"samples_omitted": [NSNumber numberWithBool:samplesOmitted]',
                  '@"observations_qualify_pass": [NSNumber numberWithBool:NO]',
                  '@"manual_review_required": [NSNumber numberWithBool:YES]',
                  '@"automatic_page_qualification": [NSNumber numberWithBool:NO]',
                  '@"runtime_precise_url": @"UNKNOWN"',
                  'manualReceipt[@"status"] = handoff == XCTWaiterResultCompleted && captureRetained ? @"manual_review_required" : @"UNKNOWN";',
                  'PRIVACY_BROWSER_STATE_PAIRS:UNKNOWN bounded serialization unavailable',
                  'PRIVACY_BROWSER_MANUAL_RECEIPT:UNKNOWN bounded serialization unavailable'):
        if token not in case:
            raise ValueError('Missing unchanged deadline, failure guard or bounded honest manual receipt')
    if (case.index('PRIVACY_BROWSER_STATE_PAIRS:%@') >= case.index('XCTAssertEqual(handoff,') or
            case.index('PRIVACY_BROWSER_MANUAL_RECEIPT:%@') >= case.index('XCTAssertEqual(handoff,')):
        raise ValueError('Failed assertion must retain the bounded observations')
    tail = case[case.index('    [self.app activate];'):]
    if hashlib.sha256(tail.encode()).hexdigest() != '9c787ede9aa255b2536f03c0097c7c56d9e7d01e47d7ea7278790736d0c76752':
        raise ValueError('Changed privacy return, close or scanner/history restoration')
    restore_phone_for_historical_observer(source)



PHONE_READINESS_HELPER_SHA256 = '8a6ab80d971daa1be51f0201103ddc22bc96152bf402139281d6a886cee73f0b'
PHONE_READINESS_METHOD_REPLACEMENTS = [{'selector': 'assertOfflinePrivacyForChinese:', 'new_sha256': '34c1011eedb5350d313dcbf599840f2559b70275e962f09d0032c6ecb951db43', 'old': '- (void)assertOfflinePrivacyForChinese:(BOOL)Chinese {\n    XCUIElementQuery *bodies = [self.app.staticTexts matchingIdentifier:@"privacy.body"];\n    XCUIElement *body = bodies.firstMatch;\n    XCTAssertTrue([body waitForExistenceWithTimeout:5]);\n    XCTAssertEqual(bodies.count, 1);\n    NSString *approved = Chinese ? @"Celluloid、QRCatcher 和 TouchColor 在设备本地处理照片、相机画面、二维码或颜色数据，开发者不收集或上传这些数据。用户主动分享、打开链接，以及系统 iCloud 同步等行为由相应服务处理。如有隐私问题，请联系 100mango@gmail.com。本地数据可通过相应应用或系统删除，权限可在系统设置中撤回。" : @"Celluloid, QRCatcher, and TouchColor process photos, camera images, QR codes, or color data locally on your device. The developer does not collect or upload this data. Actions you choose to take, such as sharing or opening links, and system services such as iCloud sync are handled by the respective services. For privacy questions, contact 100mango@gmail.com. Local data can be deleted through the relevant app or system, and permissions can be revoked in system settings.";\n    XCTAssertEqualObjects(body.label, approved);\n    XCTAssertEqual(self.app.webViews.count, 0, @"The default local policy must not create a web document.");\n    XCTAssertEqual(self.app.state, XCUIApplicationStateRunningForeground);\n    XCUIElement *content = self.app.scrollViews[@"privacy.content"];\n    XCUIElement *actions = self.app.scrollViews[@"privacy.actionScroll"];\n    CGRect viewport = CGRectIntersection(self.app.frame, content.frame);\n    XCTAssertFalse(CGRectIsEmpty(viewport));\n    XCTAssertGreaterThan(CGRectGetHeight(body.frame), 0);\n    XCTAssertGreaterThan(CGRectGetWidth(body.frame), 0);\n    XCTAssertGreaterThanOrEqual(CGRectGetMinX(body.frame), CGRectGetMinX(viewport));\n    XCTAssertLessThanOrEqual(CGRectGetMaxX(body.frame), CGRectGetMaxX(viewport));\n    CGRect beginning = CGRectMake(CGRectGetMinX(body.frame), CGRectGetMinY(body.frame), CGRectGetWidth(body.frame), MIN(20, CGRectGetHeight(body.frame)));\n    XCTAssertTrue(CGRectContainsRect(viewport, beginning), @"The approved text must begin visibly in the real scroll pane.");\n    XCUIElement *external = self.app.buttons[@"privacy.externalPolicy"];\n    XCTAssertEqualObjects(external.label, Chinese ? @"在浏览器打开" : @"Open in Browser");\n    for (NSUInteger attempt = 0; attempt < 2; attempt++) {\n        if (external.hittable && CGRectContainsRect(actions.frame, external.frame)) break;\n        [actions swipeUp];\n    }\n    XCTAssertTrue(external.hittable);\n    XCTAssertTrue(CGRectContainsRect(actions.frame, external.frame));\n    XCTAssertTrue(CGRectContainsRect(viewport, beginning), @"Action scrolling must preserve the visible local text.");\n    XCTAssertTrue(self.app.navigationBars.buttons[@"privacy.close"].hittable);\n    NSError *error = nil;\n    XCTAssertTrue([self.app performAccessibilityAuditWithAuditTypes:XCUIAccessibilityAuditTypeAll issueHandler:nil error:&error], @"Offline privacy accessibility audit: %@", error);\n}\n'}, {'selector': 'testDeniedCameraAndEmptyHistory', 'new_sha256': 'bd1f1b1b9245d41a7a05e0f1c8b1efa225705397ed5135e7d121ca70b1c1c1ba', 'old': '- (void)testDeniedCameraAndEmptyHistory {\n    [self launch:@[@"-reset-history", @"-camera-denied"]];\n    XCTAssertTrue([self.app.buttons[@"scan.settings"] waitForExistenceWithTimeout:10]);\n    XCTAssertTrue([self.app.staticTexts[@"scan.status"].label containsString:@"Camera access is off"]);\n    XCUIElement *privacy = self.app.navigationBars.buttons[@"privacy.policy"];\n    XCTAssertTrue(privacy.hittable);\n    XCTAssertEqualObjects(privacy.label, @"Privacy Policy");\n    [privacy tap];\n    XCUIElement *done = self.app.navigationBars.buttons[@"privacy.close"];\n    XCTAssertTrue([done waitForExistenceWithTimeout:15]);\n    [self assertOfflinePrivacyForChinese:NO];\n    NSLog(@"PRIVACY_OPEN_UI:%@", self.app.debugDescription);\n    [self logSyntheticScreenshot:@"privacy-open-diagnostic"];\n    [self.app.buttons[@"privacy.externalPolicy"] tap];\n    XCUIApplication *browser = [[XCUIApplication alloc] initWithBundleIdentifier:@"com.apple.mobilesafari"];\n    NSPredicate *browserForeground = [NSPredicate predicateWithBlock:^BOOL(id object, NSDictionary *bindings) {\n        (void)object; (void)bindings;\n        return browser.state == XCUIApplicationStateRunningForeground &&\n            (self.app.state == XCUIApplicationStateRunningBackground || self.app.state == XCUIApplicationStateRunningBackgroundSuspended);\n    }];\n    XCTNSPredicateExpectation *openedOutside = [[XCTNSPredicateExpectation alloc] initWithPredicate:browserForeground object:browser];\n    XCTAssertEqual([XCTWaiter waitForExpectations:@[openedOutside] timeout:10], XCTWaiterResultCompleted, @"Only the explicit policy button opens an external browser.");\n    [self.app activate];\n    XCTAssertTrue([done waitForExistenceWithTimeout:10]);\n    [self assertOfflinePrivacyForChinese:NO];\n    [done tap];\n    BOOL returnedToScanner = [self.app.buttons[@"scan.settings"] waitForExistenceWithTimeout:5];\n    if (!returnedToScanner) {\n        NSLog(@"PRIVACY_RETURN_UI:%@", self.app.debugDescription);\n        [self logSyntheticScreenshot:@"privacy-return-diagnostic"];\n    }\n    XCTAssertTrue(returnedToScanner);\n    [self.app.tabBars.buttons[@"history.tab"] tap];\n    XCTAssertTrue([self.app.staticTexts[@"history.empty"] waitForExistenceWithTimeout:5]);\n    XCTAssertTrue(self.app.navigationBars.buttons[@"privacy.policy"].hittable);\n    [self.app.tabBars.buttons[@"scan.tab"] tap];\n    XCTAssertTrue(self.app.buttons[@"scan.settings"].exists);\n}\n'}]
PHONE_BROWSER_WINDOW_BLOCKS = [{'name': 'import', 'new': '#import <math.h>\n', 'sha256': '96a4cc35888f13a108e3f9ca0c7b42699961ebd9910b2ffac58b8fb3485840a2'}, {'name': 'property', 'new': '@property (nonatomic) BOOL privacyBrowserObservationLate;\n@property (nonatomic) BOOL privacyBrowserCaptureUnknown;\n', 'sha256': '1bea3334ff9fca0dd26141c043d1b7b259bd7ae5439341564fb48e95838d3da8'}, {'name': 'setup', 'new': '    self.privacyBrowserObservationLate = NO;\n    self.privacyBrowserCaptureUnknown = NO;\n', 'sha256': '26fba94d6307e61b7e30a57d85af323670afeffe73597a876ca8f179379ba73b'}, {'name': 'late_guard', 'new': '    if (self.privacyBrowserObservationLate || self.privacyBrowserCaptureUnknown) {\n        // A late observation or unavailable capture leaves the handoff UNKNOWN. Stop all further\n        // test-authored AX reads/device actions while preserving XCTest cleanup.\n        [super tearDown];\n        if (self.cameraMonitor) [self removeUIInterruptionMonitor:self.cameraMonitor];\n        [self removeUIInterruptionMonitor:self.interruptionGuard];\n        return;\n    }\n', 'sha256': '6e2c96b45afad540973db1ef06be246b9990caa86d0e707b4bfc450e9a5952df'}]
PAD_SHARE_OBSERVATION_BLOCKS = [{'name': 'properties', 'new': '@property (nonatomic) BOOL shareSystemObservationAttempted;\n@property (nonatomic) BOOL shareSystemObservationLate;\n', 'sha256': '7420ecc4688453962145d6867bddecb0409ea32ce2f8f97145edfc9bd02a19ec'}, {'name': 'setup', 'new': '    self.shareSystemObservationAttempted = NO; self.shareSystemObservationLate = NO;\n', 'sha256': '13510ef96ac74b8e5e44724ebb91ce9ee6657fe278dc93d3ee541e99a3549dee'}, {'name': 'late_guard', 'new': '    if (self.shareSystemObservationLate) {\n        // A returned late system observation cannot justify another AX read or\n        // a test-authored device action. The already-failed case stays failed.\n        [super tearDown];\n        [self removeUIInterruptionMonitor:self.interruptionGuard];\n        return;\n    }\n', 'sha256': '9ae65d32e23cc39dccfa5d11b25cb570374836ae95826ff4fa19eb28fcb3cfeb'}, {'name': 'helper', 'new': '- (void)retainSpringboardShareObservation {\n    if (self.shareSystemObservationAttempted) return;\n    self.shareSystemObservationAttempted = YES;\n    NSTimeInterval started = NSProcessInfo.processInfo.systemUptime;\n    NSMutableDictionary *record = [@{@"version": @1, @"scope": @"springboard_unique_ActivityListView",\n        @"status": @"UNKNOWN", @"observations_qualify_pass": [NSNumber numberWithBool:NO],\n        @"activity_count": NSNull.null, @"activity_frame": NSNull.null,\n        @"payload_count": NSNull.null, @"payload_frame": NSNull.null,\n        @"copy_count": NSNull.null, @"copy_enabled": NSNull.null,\n        @"copy_hittable": NSNull.null, @"copy_frame": NSNull.null} mutableCopy];\n    // Each public AX getter may block until the unchanged case/outer timeout.\n    // A late return stops this observation and all later test-authored reads.\n    BOOL (^timely)(void) = ^BOOL {\n        NSTimeInterval elapsed = NSProcessInfo.processInfo.systemUptime - started;\n        BOOL valid = isfinite(elapsed) && elapsed >= 0 && elapsed < 10;\n        if (!valid) self.shareSystemObservationLate = YES;\n        return valid;\n    };\n    id (^frameValue)(CGRect) = ^id(CGRect frame) {\n        return QRPadFiniteNonemptyRect(frame) ? (id)@[@(frame.origin.x), @(frame.origin.y), @(frame.size.width), @(frame.size.height)] : (id)NSNull.null;\n    };\n    NSLog(@"IPAD_SHARE_SPRINGBOARD_OBSERVATION_ENTER unqualified");\n    do {\n        XCUIApplication *system = [[XCUIApplication alloc] initWithBundleIdentifier:@"com.apple.springboard"];\n        XCUIElementQuery *activities = [system.otherElements matchingIdentifier:@"ActivityListView"];\n        if (!timely()) break;\n        NSUInteger activityCount = activities.count;\n        record[@"activity_count"] = @(activityCount);\n        if (!timely() || activityCount != 1) break;\n        XCUIElement *activity = activities.firstMatch;\n        CGRect activityFrame = activity.frame;\n        record[@"activity_frame"] = frameValue(activityFrame);\n        if (!timely() || !QRPadFiniteNonemptyRect(activityFrame)) break;\n        XCUIElementQuery *payloads = [activity.otherElements matchingPredicate:[NSPredicate predicateWithFormat:@"label == %@", @"Native iPad QR result 你好"]];\n        NSUInteger payloadCount = payloads.count;\n        record[@"payload_count"] = @(payloadCount);\n        if (!timely()) break;\n        if (payloadCount == 1) {\n            record[@"payload_frame"] = frameValue(payloads.firstMatch.frame);\n            if (!timely()) break;\n        }\n        XCUIElementQuery *copies = [[activity.cells matchingIdentifier:@"actionGroupCell"]\n            containingPredicate:[NSPredicate predicateWithFormat:@"elementType == %lu AND identifier == %@ AND label == %@",\n                (unsigned long)XCUIElementTypeStaticText, @"cellTitleLabel", @"Copy"]];\n        NSUInteger copyCount = copies.count;\n        record[@"copy_count"] = @(copyCount);\n        if (!timely()) break;\n        if (copyCount == 1) {\n            XCUIElement *copy = copies.firstMatch;\n            record[@"copy_enabled"] = [NSNumber numberWithBool:copy.enabled];\n            if (!timely()) break;\n            record[@"copy_hittable"] = [NSNumber numberWithBool:copy.hittable];\n            if (!timely()) break;\n            record[@"copy_frame"] = frameValue(copy.frame);\n            if (!timely()) break;\n        }\n        record[@"status"] = @"scoped_observation_only";\n    } while (NO);\n    record[@"late_return"] = [NSNumber numberWithBool:self.shareSystemObservationLate];\n    NSTimeInterval elapsed = NSProcessInfo.processInfo.systemUptime - started;\n    record[@"elapsed"] = isfinite(elapsed) && elapsed >= 0 ? (id)@(elapsed) : (id)NSNull.null;\n    NSData *data = [NSJSONSerialization dataWithJSONObject:record options:NSJSONWritingSortedKeys error:nil];\n    if (data && data.length <= 3072) {\n        NSLog(@"IPAD_SHARE_SPRINGBOARD_OBSERVATION:%@", [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding]);\n    } else {\n        NSLog(@"IPAD_SHARE_SPRINGBOARD_OBSERVATION:UNKNOWN bounded serialization unavailable");\n    }\n}\n', 'sha256': 'a196957ba8d739a589c797743ed30b7bbe86219a65848766b2f38816008e52c4'}, {'name': 'call', 'new': '    if (readiness != XCTWaiterResultCompleted) [self retainSpringboardShareObservation];\n', 'sha256': 'af583824c9f3e3dfecbd5b8017632c852306b6d9f634b7384e8a19030aa52de1'}]

def restore_phone_for_historical_observer(text):
    """Remove only the exact admitted observer/notice clauses, retaining old proof."""
    start = 'static NSString *QRObservedApplicationStateName('
    if start not in text:
        if any(token in text for token in ('PRIVACY_BROWSER_STATE_PAIRS:', 'noticeBeginning',
                                         'privacyBrowserObservationLate', 'QRPrivacyBrowserWindowQualifies',
                                         'PRIVACY_BROWSER_MANUAL_RECEIPT:', 'privacyBrowserCaptureUnknown',
                                         'QRPrivacyManualCaptureRetainable')):
            raise ValueError('Incomplete phone readiness observation')
        return text
    if text.count(start) != 1:
        raise ValueError('Ambiguous phone readiness helper')
    begin = text.index(start)
    end = text.index('@interface', begin)
    helper = text[begin:end]
    if hashlib.sha256(helper.encode()).hexdigest() != PHONE_READINESS_HELPER_SHA256:
        raise ValueError('Changed admitted symbolic state helper')
    text = text[:begin] + text[end:]
    for entry in PHONE_BROWSER_WINDOW_BLOCKS:
        block = entry['new']
        if text.count(block) != 1 or hashlib.sha256(block.encode()).hexdigest() != entry['sha256']:
            raise ValueError('Changed admitted browser manual capture import or cleanup clause')
        text = text.replace(block, '', 1)
    for entry in PHONE_READINESS_METHOD_REPLACEMENTS:
        current = method(text, entry['selector'])
        if hashlib.sha256(current.encode()).hexdigest() != entry['new_sha256']:
            raise ValueError('Changed admitted phone readiness or notice method')
        text = text.replace(current, entry['old'], 1)
    return text


def restore_pad_share_observation(text):
    """Historical inputs never erase an unpinned new diagnostic or other behavior."""
    if 'shareSystemObservationAttempted' not in text:
        if 'retainSpringboardShareObservation' in text:
            raise ValueError('Incomplete iPad share observation')
        return text
    for entry in PAD_SHARE_OBSERVATION_BLOCKS:
        block = entry['new']
        if text.count(block) != 1 or hashlib.sha256(block.encode()).hexdigest() != entry['sha256']:
            raise ValueError('Changed admitted iPad share diagnostic block')
        text = text.replace(block, '', 1)
    return text



UNIT_PRIVACY_HELPER_SHA256 = 'f87128dad627b7b12df8969ccb0e883a61836f828d73329112690304d718a491'
UNIT_PRIVACY_CALLS = '    [self assertPrivacyWebsiteNoticeAtCompactWidthForCategory:UIContentSizeCategoryLarge];\n    [self assertPrivacyWebsiteNoticeAtCompactWidthForCategory:UIContentSizeCategoryAccessibilityExtraExtraExtraLarge];\n'

def restore_unit_for_historical_observer(text):
    """Keep the old unit inventory proof while binding this exact added exercise."""
    marker = '- (void)assertPrivacyWebsiteNoticeAtCompactWidthForCategory:'
    if marker not in text:
        if 'assertPrivacyWebsiteNoticeAtCompactWidthForCategory:' in text:
            raise ValueError('Incomplete privacy geometry exercise')
        return text
    if (text.count(marker) != 1 or text.count(UNIT_PRIVACY_CALLS) != 1 or
            text.count('#import <math.h>\n#import <float.h>\n') != 1):
        raise ValueError('Ambiguous new privacy geometry exercise')
    begin = text.index(marker)
    end = text.index('- (void)testPrivacyOfflineBodyAndExplicitBrowserActionKeepCloseIdempotent {', begin)
    helper = text[begin:end]
    if hashlib.sha256(helper.encode()).hexdigest() != UNIT_PRIVACY_HELPER_SHA256:
        raise ValueError('Changed admitted compact privacy geometry helper')
    return (text[:begin]+text[end:]).replace(UNIT_PRIVACY_CALLS, '', 1).replace('#import <math.h>\n#import <float.h>\n', '', 1)


def compiled_constraint_precision(unit, product, scalar):
    """Exercise the native operands with real C float storage, without UIKit."""
    helper = method(unit, 'assertPrivacyWebsiteNoticeAtCompactWidthForCategory:')
    calls = re.findall(r'XCTAssertEqualWithAccuracy\(constraint\.multiplier, ([^,\n]+), ([^;\n]+)\);', helper)
    if (len(calls) != 1 or helper.count('XCTAssertTrue(isfinite(constraint.multiplier));') != 1 or
            unit.count('#import <math.h>\n#import <float.h>\n') != 1):
        raise ValueError('Missing finite native constraint comparison or imports')
    expected, epsilon = calls[0]
    expression = r'(?:FLT_EPSILON|DBL_EPSILON|[0-9.eE+\-]+)(?:\s*\*\s*[0-9.]+)?'
    if any(re.fullmatch(expression, operand) is None for operand in calls[0]):
        raise ValueError('Unsupported constraint comparison operand')
    ratios = re.findall(r'\[actionScroll\.heightAnchor constraintLessThanOrEqualToAnchor:safe\.heightAnchor multiplier:([0-9.]+)\]', product)
    if len(ratios) != 1 or scalar not in ('float', 'double'):
        raise ValueError('Missing unique product constraint or portable scalar')
    compiler = shutil.which('cc')
    if not compiler:
        raise RuntimeError('A real portable C compiler is required')
    program = '''#include <float.h>
#include <math.h>
#include <stdio.h>
typedef SCALAR PortableCGFloat;
static int qualifies(PortableCGFloat value) {
    return isfinite(value) && fabs((double)value - (EXPECTED)) <= (EPSILON);
}
int main(void) {
    /* Model the retained public multiplier after float32 storage, even when
       the public CGFloat-equivalent getter widens it back to double. */
    volatile float stored = (float)(RATIO);
    PortableCGFloat multiplier = stored;
    PortableCGFloat retained = (PortableCGFloat)0.449999988079;
    printf("{\\"scalar_bits\\":%zu,\\"expected\\":%.17g,\\"epsilon\\":%.17g,"
           "\\"stored_multiplier\\":%.17g,\\"stored_qualifies\\":%d,"
           "\\"retained_qualifies\\":%d,\\"wrong_qualifies\\":[%d,%d,%d,%d,%d,%d,%d,%d]}\\n",
           sizeof(PortableCGFloat) * 8, (double)(EXPECTED), (double)(EPSILON),
           (double)multiplier, qualifies(multiplier), qualifies(retained),
           qualifies(0.5), qualifies(0.44), qualifies(0.450001), qualifies(-0.45),
           qualifies(0), qualifies(NAN), qualifies(INFINITY), qualifies(-INFINITY));
    return 0;
}
'''
    program = (program.replace('SCALAR', scalar).replace('EXPECTED', expected)
               .replace('EPSILON', epsilon).replace('RATIO', ratios[0]))
    with tempfile.TemporaryDirectory() as directory:
        executable = str(Path(directory)/'constraint-precision')
        subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
                        '-x', 'c', '-', '-o', executable, '-lm'], input=program,
                       text=True, capture_output=True, check=True, timeout=10)
        result = subprocess.run([executable], text=True, capture_output=True,
                                check=True, timeout=10)
    return json.loads(result.stdout)


def compiled_browser_window_predicates(phone, scalar):
    """Execute pinned legacy frame helpers plus the current deadline/capture guards."""
    names = ('QRPrivacyFiniteNonemptyRect', 'QRPrivacyObservationTimely',
             'QRPrivacyBrowserWindowQualifies', 'QRPrivacyManualCaptureRetainable')
    helpers = []
    for name in names:
        matches = re.findall(r'^static BOOL ' + name + r'\([^\n]+\) \{\n.*?^\}', phone, re.M | re.S)
        if len(matches) != 1:
            raise ValueError('Missing unique native pure browser helper: ' + name)
        helpers.append(matches[0])
    if scalar not in ('float', 'double'):
        raise ValueError('Unsupported portable frame scalar')
    compiler = shutil.which('cc')
    if not compiler:
        raise RuntimeError('A real portable C compiler is required')
    program = r'''#include <float.h>
#include <math.h>
#include <stdio.h>
typedef int BOOL;
typedef double NSTimeInterval;
typedef size_t NSUInteger;
typedef SCALAR PortableCGFloat;
typedef struct { PortableCGFloat x, y; } CGPoint;
typedef struct { PortableCGFloat width, height; } CGSize;
typedef struct { CGPoint origin; CGSize size; } CGRect;
/* Symbolic surrogate states deliberately use no Apple raw-value ordering. */
typedef enum { XCUIApplicationStateUnknown = 19, XCUIApplicationStateNotRunning = 7,
    XCUIApplicationStateRunningBackground = 31, XCUIApplicationStateRunningBackgroundSuspended = 11,
    XCUIApplicationStateRunningForeground = 23 } XCUIApplicationState;
HELPERS
int main(void) {
    CGRect frame = {{0, 0}, {390, 844}};
    CGRect invalid[] = {{{NAN, 0}, {390, 844}}, {{0, NAN}, {390, 844}},
        {{0, 0}, {NAN, 844}}, {{0, 0}, {390, NAN}},
        {{INFINITY, 0}, {390, 844}}, {{0, 0}, {390, INFINITY}},
        {{0, 0}, {0, 844}}, {{0, 0}, {390, 0}},
        {{0, 0}, {-390, 844}}, {{0, 0}, {390, -844}},
        {{LIMIT, 0}, {LIMIT, 844}}, {{0, LIMIT}, {390, LIMIT}}};
    XCUIApplicationState states[] = {XCUIApplicationStateUnknown, XCUIApplicationStateNotRunning,
        XCUIApplicationStateRunningBackground, XCUIApplicationStateRunningBackgroundSuspended};
    NSTimeInterval late[] = {110, 111, 99, NAN, INFINITY, -INFINITY};
    printf("{\"scalar_bits\":%zu,\"positive\":%d,\"invalid_frames\":[", sizeof(PortableCGFloat) * 8,
           QRPrivacyBrowserWindowQualifies(XCUIApplicationStateRunningForeground, 1, frame, 1));
    for (size_t i = 0; i < sizeof(invalid) / sizeof(invalid[0]); i++)
        printf("%s%d", i ? "," : "", QRPrivacyBrowserWindowQualifies(XCUIApplicationStateRunningForeground, 1, invalid[i], 1));
    printf("],\"wrong_states\":[");
    for (size_t i = 0; i < sizeof(states) / sizeof(states[0]); i++)
        printf("%s%d", i ? "," : "", QRPrivacyBrowserWindowQualifies(states[i], 1, frame, 1));
    /* Hidden, off-screen and covered windows each have public hittable false. */
    printf("],\"missing_hidden_covered\":[%d,%d,%d],\"timely\":[%d,%d],\"late_getter_returns\":[",
        QRPrivacyBrowserWindowQualifies(XCUIApplicationStateRunningForeground, 0, frame, 1),
        QRPrivacyBrowserWindowQualifies(XCUIApplicationStateRunningForeground, 1, frame, 0),
        QRPrivacyBrowserWindowQualifies(XCUIApplicationStateRunningForeground, 1, (CGRect){{10000, 10000}, {390, 844}}, 0),
        QRPrivacyObservationTimely(100, 100), QRPrivacyObservationTimely(100, 109.999));
    for (size_t i = 0; i < sizeof(late) / sizeof(late[0]); i++)
        printf("%s%d", i ? "," : "", QRPrivacyObservationTimely(100, late[i]));
    printf("],\"invalid_start\":[%d,%d],\"capture_bounds\":[%d,%d,%d,%d,%d,%d]}\n",
           QRPrivacyObservationTimely(NAN, 100), QRPrivacyObservationTimely(INFINITY, INFINITY),
           QRPrivacyManualCaptureRetainable(1179, 2556, 1),
           QRPrivacyManualCaptureRetainable(1179, 2556, 500 * 1024),
           QRPrivacyManualCaptureRetainable(0, 2556, 1),
           QRPrivacyManualCaptureRetainable(1179, 0, 1),
           QRPrivacyManualCaptureRetainable(1179, 2556, 0),
           QRPrivacyManualCaptureRetainable(1179, 2556, 500 * 1024 + 1));
    return 0;
}
'''
    program = (program.replace('SCALAR', scalar).replace('LIMIT', 'FLT_MAX' if scalar == 'float' else 'DBL_MAX')
               .replace('HELPERS', '\n'.join(helpers)))
    with tempfile.TemporaryDirectory() as directory:
        executable = str(Path(directory)/'browser-window-predicates')
        subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
                        '-x', 'c', '-', '-o', executable, '-lm'], input=program,
                       text=True, capture_output=True, check=True, timeout=10)
        result = subprocess.run([executable], text=True, capture_output=True,
                                check=True, timeout=10)
    return json.loads(result.stdout)


class OfflinePrivacyTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT/'QRCatcher/QRPrivacyViewController.m').read_text()
        self.unit = (ROOT/'QRCatcherTests/QRCatcherTests.m').read_text()
        self.phone = (ROOT/'QRCatcherUITests/QRCatcherUITests.m').read_text()
        self.pad = (ROOT/'QRCatcherUITests/QRCatcherPadUITests.m').read_text()

    def test_approved_english_chinese_core_copy_is_exact_not_a_new_promise(self):
        shared = (ROOT/'Shared/Services/QRPrivacyText.swift').read_text()
        english = re.search(r'static let english = "([^"\n]*)"', shared)[1]
        chinese = re.search(r'static let simplifiedChinese = "([^"\n]*)"', shared)[1]
        self.assertIn('[self label:@"'+english+'" identifier:@"privacy.body"', self.source)
        localized = (ROOT/'QRCatcher/zh-Hans.lproj/Localizable.strings').read_text()
        self.assertIn('"'+english+'" = "'+chinese+'";', localized)
        self.assertIn('GitHub Pages records visitor IP addresses for security.', self.source)
        self.assertIn('System backups, file providers, the clipboard', self.source)

    def test_default_offline_and_explicit_public_browser_boundary(self):
        default_contract(self.source)
        self.assertIn('@selector(openPolicyInBrowser)', method(self.source, 'viewDidLoad'))
        for mutation in ('[self openPolicyInBrowser];', 'WKWebView *unexpected;', 'NSURLSession *unexpected;'):
            changed = self.source.replace('[super viewDidLoad];', '[super viewDidLoad]; '+mutation, 1)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                default_contract(changed)
        for before, after in [('if (self.closing || self.opening) return;', 'if (self.closing) return;'),
                              ('https://100mango.github.io/app-privacy/', 'https://example.com/'),
                              ('if (!strongSelf || strongSelf.closing) return;', 'if (!strongSelf) return;')]:
            with self.subTest(mutation=before), self.assertRaises(ValueError):
                default_contract(self.source.replace(before, after, 1))

    def test_dynamic_type_scroll_ownership_and_unchanged_close_transition_contract(self):
        for token in ('label.numberOfLines = 0;', 'label.adjustsFontForContentSizeCategory = YES;',
                      'UIColor.labelColor', 'UIFontTextStyleBody', 'UIFontTextStyleFootnote',
                      '[QRActionButton buttonWithType:UIButtonTypeSystem]', 'UIFontTextStyleHeadline',
                      'content.contentLayoutGuide', 'content.frameLayoutGuide',
                      'actionScroll.contentLayoutGuide', 'actionScroll.frameLayoutGuide'):
            self.assertIn(token, self.source)
        closing = method(self.source, 'close')
        for token in ('if (self.closing) return;', 'self.closing = YES;', 'if (cleanup) cleanup();',
                      'dismissViewControllerAnimated:YES completion:cleanup', 'presentation.transitionCoordinator'):
            self.assertIn(token, closing)
        self.assertNotIn('stopLoading', closing)

    def test_same_native_case_inventory_and_unrelated_method_bodies_remain_exact(self):
        for path, reference in NATIVE_REFERENCE.items():
            text = (ROOT/path).read_text()
            if path.endswith('QRCatcherPadUITests.m'):
                text = restore_pad_share_observation(text)
            actual = test_methods(text)
            expected = set(reference['all_case_names'])
            if path.endswith('QRCatcherTests.m'):
                expected.remove('testPrivacyHTTPFailuresAndWebProcessTerminationOfferRetry')
                expected.add('testPrivacyOfflineBodyAndExplicitBrowserActionKeepCloseIdempotent')
            self.assertEqual(set(actual), expected, path)
            for name, digest in reference['unchanged_method_sha256'].items():
                self.assertEqual(hashlib.sha256(actual[name].encode()).hexdigest(), digest, path+':'+name)
        for name, count in [('QRCatcherTests.m', 12), ('QRBoundedImageImportTests.m', 7),
                            ('QRPhoneResultTests.m', 7), ('QRWatchPhoneServiceTests.m', 4)]:
            self.assertEqual(len(test_methods((ROOT/'QRCatcherTests'/name).read_text())), count)

    def test_real_unit_action_default_no_open_pending_failure_success_and_late_close(self):
        case = test_methods(self.unit)['testPrivacyOfflineBodyAndExplicitBrowserActionKeepCloseIdempotent']
        for token in ('privacy.openedURLs.count, 0', '[open sendActionsForControlEvents:UIControlEventTouchUpInside]',
                      'privacy.openedURLs.count, 1', 'privacy.pendingCompletion(NO)', 'privacy.pendingCompletion(YES)',
                      'privacy.openedURLs.count, 3', '[privacy close]; [privacy close];', 'reopened.openedURLs.count, 0'):
            self.assertIn(token, case)
        self.assertLess(case.index('privacy.openedURLs.count, 0'), case.index('[open sendActionsForControlEvents:'))
        self.assertIn('- (void)openExternalURL:(NSURL *)URL completion:(void (^)(BOOL))completion', self.unit)
        self.assertNotIn('WKNavigationResponse', self.unit)

    def test_phone_real_external_browser_return_and_both_languages_keep_all_audits(self):
        case = test_methods(self.phone)['testDeniedCameraAndEmptyHistory']
        for token in ('[self.app.buttons[@"privacy.externalPolicy"] tap]', 'com.apple.mobilesafari',
                      'browser.state', 'XCUIScreen.mainScreen.screenshot.image', '[self.app activate]',
                      '[self assertOfflinePrivacyForChinese:NO]', '[done tap]'):
            self.assertIn(token, case)
        self.assertIn('[self assertOfflinePrivacyForChinese:YES]', self.phone)
        self.assertIn('Offline privacy accessibility audit:', self.phone)
        self.assertIn('CGRectContainsRect(actions.frame, external.frame)', self.phone)
        self.assertIn('iPad largest-text offline privacy accessibility audit:', self.pad)
        self.assertIn('issueHandler:nil', self.phone)
        self.assertIn('issueHandler:nil', self.pad)
        self.assertEqual(self.pad.count(PAD_START), 1)

    def test_browser_proxy_precedes_action_without_launch_or_weakening_handoff(self):
        browser_observation_contract(self.phone)
        observer = '    XCUIApplication *browser = [[XCUIApplication alloc] initWithBundleIdentifier:@"com.apple.mobilesafari"];\n'
        action = '    [self.app.buttons[@"privacy.externalPolicy"] tap];\n'
        after_tap = self.phone.replace(observer, '', 1).replace(action, action+observer, 1)
        for changed in (after_tap, self.phone.replace(action, '    [browser activate];\n'+action, 1),
                        self.phone.replace(action, '    [browser launch];\n'+action, 1)):
            with self.subTest(mutation=changed != after_tap), self.assertRaises(ValueError):
                browser_observation_contract(changed)

    def test_browser_states_are_single_snapshots_and_diagnostics_cannot_qualify(self):
        browser_observation_contract(self.phone)
        changes = [('XCUIApplicationState browserState = browser.state;', 'XCUIApplicationState browserState = browser.state; (void)browser.state;'),
                   ('waitForExpectations:@[openedOutside] timeout:10];', 'waitForExpectations:@[openedOutside] timeout:11];'),
                   ('statePairs.count < 12', 'statePairs.count < 13'),
                   ('stateTraceData.length <= 2048', 'stateTraceData.length <= 2049'),
                   ('[NSNumber numberWithBool:NO]', '[NSNumber numberWithBool:YES]'),
                   ('return browserState == XCUIApplicationStateRunningForeground;', 'return YES;'),
                   ('return browserState == XCUIApplicationStateRunningForeground;', 'return browserState == XCUIApplicationStateRunningForeground && browser.windows.firstMatch.exists;'),
                   ('return browserState == XCUIApplicationStateRunningForeground;', 'return browserState == XCUIApplicationStateRunningForeground && self.app.state == XCUIApplicationStateRunningBackground;'),
                   ('[done tap];', '/* removed close */')]
        for before, after in changes:
            with self.subTest(mutation=before), self.assertRaises(ValueError):
                browser_observation_contract(self.phone.replace(before, after, 1))

    def test_closed_symbolic_state_labels_and_twelve_pairs_fit_diagnostic_bytes(self):
        start = self.phone.index('static NSString *QRObservedApplicationStateName(')
        end = self.phone.index('static BOOL QRPrivacyFiniteNonemptyRect(', start)
        helper = self.phone[start:end]
        labels = {'NotRunning': 'not_running', 'RunningBackground': 'background',
                  'RunningBackgroundSuspended': 'suspended', 'RunningForeground': 'foreground',
                  'Unknown': 'unknown'}
        for symbol, label in labels.items():
            self.assertIn('case XCUIApplicationState'+symbol+': return @"'+label+'";', helper)
        self.assertNotRegex(helper, r'case\s+[0-9]')
        # No raw-value ordering is assumed. Even a maximum-width public enum
        # observation fits; strings/keys are fixed, never app or website text.
        samples = [{'browser_raw': 18446744073709551615, 'qr_raw': 18446744073709551615,
                    'browser_kind': 'not_running', 'qr_kind': 'not_running'}] * 12
        encoded = json.dumps({'version': 1, 'samples': samples, 'samples_omitted': True,
                              'observations_qualify_pass': False}, separators=(',', ':')).encode()
        self.assertLessEqual(len(encoded), 2048)

    def test_real_c_browser_predicate_rejects_missing_hidden_covered_invalid_and_late(self):
        for scalar, bits in [('float', 32), ('double', 64)]:
            with self.subTest(scalar=scalar):
                observed = compiled_browser_window_predicates(self.phone, scalar)
                self.assertEqual(observed['scalar_bits'], bits)
                self.assertEqual(observed['positive'], 1)
                self.assertEqual(observed['invalid_frames'], [0] * 12)
                self.assertEqual(observed['wrong_states'], [0] * 4)
                self.assertEqual(observed['missing_hidden_covered'], [0] * 3)
                self.assertEqual(observed['timely'], [1, 1])
                self.assertEqual(observed['late_getter_returns'], [0] * 6)
                self.assertEqual(observed['invalid_start'], [0, 0])
                self.assertEqual(observed['capture_bounds'], [1, 1, 0, 0, 0, 0])

    def test_real_c_mutations_expose_weakened_exists_hittable_finite_frame_or_deadline(self):
        mutations = [('&& exists &&', '&& (exists || 1) &&', 'missing_hidden_covered', 0),
                     ('QRPrivacyFiniteNonemptyRect(frame) && hittable;',
                      'QRPrivacyFiniteNonemptyRect(frame) && (hittable || 1);', 'missing_hidden_covered', 1),
                     ('frame.size.width > 0', 'frame.size.width >= 0', 'invalid_frames', 6),
                     ('isfinite(frame.origin.x + frame.size.width)', '1', 'invalid_frames', 10),
                     ('elapsed < 10;', 'elapsed < 11;', 'late_getter_returns', 0),
                     ('bytes <= 500 * 1024;', 'bytes <= 501 * 1024;', 'capture_bounds', 5),
                     ('bytes > 0', '(bytes || 1)', 'capture_bounds', 4),
                     ('return width > 0', 'return (width || 1)', 'capture_bounds', 2),
                     ('height > 0 && bytes', '(height || 1) && bytes', 'capture_bounds', 3)]
        for before, after, field, index in mutations:
            changed = self.phone.replace(before, after, 1)
            with self.subTest(mutation=before):
                self.assertNotEqual(changed, self.phone)
                with self.assertRaises(ValueError):
                    restore_phone_for_historical_observer(changed)
                observed = compiled_browser_window_predicates(changed, 'double')
                self.assertEqual(observed[field][index], 1)

    def test_safari_owner_query_real_tap_visibility_and_all_return_clauses_cannot_be_erased(self):
        mutations = [
            ('initWithBundleIdentifier:@"com.apple.mobilesafari"', 'initWithBundleIdentifier:@"com.apple.springboard"'),
            ('return browserState == XCUIApplicationStateRunningForeground;', 'return YES;'),
            ('UIImage *image = XCUIScreen.mainScreen.screenshot.image;', 'UIImage *image = self.app.screenshot.image;'),
            ('UIImage *image = XCUIScreen.mainScreen.screenshot.image;', 'UIImage *image = XCUIScreen.mainScreen.screenshot.image; (void)XCUIScreen.mainScreen.screenshot;'),
            ('if (handoff == XCTWaiterResultCompleted && timely())', 'if (handoff == XCTWaiterResultCompleted)'),
            ('if (timely() && image.CGImage)', 'if (image.CGImage)'),
            ('CGImageGetWidth(image.CGImage)', '(size_t)1440'),
            ('CGImageGetHeight(image.CGImage)', '(size_t)1440'),
            ('UIImageJPEGRepresentation(image, 0.55)', 'UIImageJPEGRepresentation(image, 0.25)'),
            ('if (timely() && QRPrivacyManualCaptureRetainable(width, height, JPEG.length))', 'if (JPEG)'),
            ('attachment.name = @"privacy-browser-manual-review";', 'attachment.name = @"privacy-browser";'),
            ('attachment.name = @"privacy-browser-manual-review";\n                    attachment.lifetime = XCTAttachmentLifetimeKeepAlways;', 'attachment.name = @"privacy-browser-manual-review";\n                    attachment.lifetime = XCTAttachmentLifetimeDeleteOnSuccess;'),
            ('captureRetained = timely();', 'captureRetained = YES;'),
            ('if (!captureRetained) self.privacyBrowserCaptureUnknown = YES;', '/* unknown capture ignored */'),
            ('if (!timely()) handoff = XCTWaiterResultTimedOut;', '/* late result ignored */'),
            ('if (self.privacyBrowserObservationLate || self.privacyBrowserCaptureUnknown) {', 'if (NO) {'),
            ('[self.app.buttons[@"privacy.externalPolicy"] tap];', '/* real tap omitted */'),
            ('XCTAssertTrue(externalPolicy.exists);', ''),
            ('XCTAssertTrue(externalPolicy.enabled);', ''),
            ('XCTAssertTrue(externalPolicy.hittable);', ''),
            ('[self.app activate];\n    XCTAssertTrue([done waitForExistenceWithTimeout:10]);', '/* return omitted */'),
            ('[done tap];', '/* Close omitted */'),
            ('@"manual_review_required": [NSNumber numberWithBool:YES]', '@"manual_review_required": [NSNumber numberWithBool:NO]'),
            ('@"automatic_page_qualification": [NSNumber numberWithBool:NO]', '@"automatic_page_qualification": [NSNumber numberWithBool:YES]'),
            ('@"runtime_precise_url": @"UNKNOWN"', '@"runtime_precise_url": @"https://100mango.github.io/app-privacy/"'),
            ('manualData.length <= 1024', 'manualData.length <= 4096'),
        ]
        for before, after in mutations:
            changed = self.phone.replace(before, after, 1)
            with self.subTest(mutation=before):
                self.assertNotEqual(changed, self.phone)
                with self.assertRaises(ValueError):
                    browser_observation_contract(changed)
                with self.assertRaises(ValueError):
                    restore_phone_for_historical_observer(changed)

    def test_window_receipt_is_once_bounded_and_keeps_runtime_address_unknown(self):
        case = test_methods(self.phone)['testDeniedCameraAndEmptyHistory']
        self.assertEqual(case.count('NSData *manualData ='), 1)
        self.assertEqual(case.count('PRIVACY_BROWSER_MANUAL_RECEIPT:%@'), 1)
        self.assertIn('@"runtime_precise_url": @"UNKNOWN"', case)
        sample = {'version': 1, 'owner': 'com.apple.mobilesafari', 'source': 'XCUIScreen.mainScreen',
                  'status': 'manual_review_required', 'runtime_precise_url': 'UNKNOWN',
                  'manual_review_required': True, 'automatic_page_qualification': False,
                  'browser_raw': 18446744073709551615, 'capture_attempts': 1,
                  'native_width': 18446744073709551615, 'native_height': 18446744073709551615,
                  'source_bytes': 500 * 1024, 'attachment_name': 'privacy-browser-manual-review',
                  'late_return': False, 'capture_unknown': False}
        encoded = json.dumps(sample, separators=(',', ':')).encode()
        self.assertLessEqual(len(encoded), 1024)
        self.assertLessEqual(2048 + len(encoded) + 256, 4096)
        guard = method(self.phone, 'tearDown').split('    if (self.testRun.failureCount > 0)', 1)[0]
        for required in ('if (self.privacyBrowserObservationLate || self.privacyBrowserCaptureUnknown)', '[super tearDown];',
                         'removeUIInterruptionMonitor:self.cameraMonitor',
                         'removeUIInterruptionMonitor:self.interruptionGuard', 'return;'):
            self.assertIn(required, guard)
        for operation in ('debugDescription', 'screenshot', 'self.app.state', '.exists',
                          '[self.app terminate]', 'orientation ='):
            self.assertNotIn(operation, guard)

    def test_website_notice_keeps_real_height_and_existing_native_case_exercises_both_categories(self):
        loaded = method(self.source, 'viewDidLoad')
        required = '[website setContentCompressionResistancePriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisVertical];'
        self.assertEqual(loaded.count(required), 1)
        self.assertIn('[actionScroll.heightAnchor constraintLessThanOrEqualToAnchor:safe.heightAnchor multiplier:0.45]', loaded)
        helper = method(self.unit, 'assertPrivacyWebsiteNoticeAtCompactWidthForCategory:')
        for token in ('CGRectMake(0, 0, 375, 593)', 'notice.bounds.size.width, 327',
                      'notice.bounds.size.height, completeNotice.height',
                      'XCTAssertTrue(isfinite(constraint.multiplier));',
                      'XCTAssertEqualWithAccuracy(constraint.multiplier, 0.45, FLT_EPSILON);', 'heightLimits, 1',
                      'CGRectContainsRect(actions.bounds, originalTarget)',
                      'actions.contentSize.height, actions.bounds.size.height',
                      'privacy.openedURLs.count, 0'):
            self.assertIn(token, helper)
        case = test_methods(self.unit)['testPrivacyOfflineBodyAndExplicitBrowserActionKeepCloseIdempotent']
        for category in ('UIContentSizeCategoryLarge', 'UIContentSizeCategoryAccessibilityExtraExtraExtraLarge'):
            self.assertIn('[self assertPrivacyWebsiteNoticeAtCompactWidthForCategory:'+category+'];', case)
        ui = method(self.phone, 'assertOfflinePrivacyForChinese:')
        for token in ('privacy.websiteNotice', 'website.label',
                      'CGRectContainsRect(actionViewport, noticeBeginning)',
                      'CGRectContainsRect(actionViewport, noticeEnding)',
                      'performAccessibilityAuditWithAuditTypes:XCUIAccessibilityAuditTypeAll issueHandler:nil'):
            self.assertIn(token, ui)
        self.assertNotIn('preferredMaxLayoutWidth', loaded)
        self.assertNotIn('adjustsFontSizeToFitWidth = YES', loaded)

    def test_real_c_float_storage_qualifies_only_machine_precision_and_finite_ratios(self):
        for scalar, bits in [('float', 32), ('double', 64)]:
            with self.subTest(scalar=scalar):
                observed = compiled_constraint_precision(self.unit, self.source, scalar)
                self.assertEqual(observed['scalar_bits'], bits)
                self.assertEqual(observed['expected'], 0.45)
                self.assertEqual(observed['epsilon'], 2 ** -23)
                self.assertEqual(observed['stored_multiplier'], 0.44999998807907104)
                self.assertEqual(observed['stored_qualifies'], 1)
                self.assertEqual(observed['retained_qualifies'], 1)
                self.assertEqual(observed['wrong_qualifies'], [0] * 8)

    def test_precision_regression_rejects_broader_narrower_and_changed_product_ratios(self):
        for scalar in ('float', 'double'):
            for epsilon in ('0', 'DBL_EPSILON', '0.1'):
                changed = self.unit.replace(', 0.45, FLT_EPSILON);', ', 0.45, '+epsilon+');', 1)
                with self.subTest(scalar=scalar, epsilon=epsilon):
                    with self.assertRaises(ValueError):
                        restore_unit_for_historical_observer(changed)
                    observed = compiled_constraint_precision(changed, self.source, scalar)
                    if epsilon == '0.1':
                        self.assertEqual(observed['wrong_qualifies'][0], 1)
                    else:
                        self.assertEqual(observed['stored_qualifies'], 0)
                        self.assertEqual(observed['retained_qualifies'], 0)
            for ratio in ('0.5', '0.44', '0.450001'):
                changed = self.source.replace('multiplier:0.45]', 'multiplier:'+ratio+']', 1)
                with self.subTest(scalar=scalar, product_ratio=ratio):
                    self.assertNotEqual(changed, self.source)
                    observed = compiled_constraint_precision(self.unit, changed, scalar)
                    self.assertEqual(observed['stored_qualifies'], 0)

    def test_precision_call_site_finite_check_and_import_mutations_cannot_be_normalized(self):
        call = 'XCTAssertEqualWithAccuracy(constraint.multiplier, 0.45, FLT_EPSILON);'
        for before, after in [(call, ''),
                              ('WithAccuracy(constraint.multiplier,', 'WithAccuracy(notice.bounds.size.width,'),
                              ('XCTAssertTrue(isfinite(constraint.multiplier));', 'XCTAssertTrue(YES);'),
                              ('#import <float.h>\n', '')]:
            changed = self.unit.replace(before, after, 1)
            with self.subTest(mutation=before):
                self.assertNotEqual(changed, self.unit)
                with self.assertRaises(ValueError):
                    restore_unit_for_historical_observer(changed)
                with self.assertRaises(ValueError):
                    compiled_constraint_precision(changed, self.source, 'double')

    def test_historical_phone_normalization_requires_every_exact_owned_clause(self):
        restored = restore_phone_for_historical_observer(self.phone)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(), 'e29e743721b4a539550cd1d563b0ec1834a368b1f2056cbc9a4c307202202648')
        for before, after in [('statePairs.count < 12', 'statePairs.count < 13'),
                              ('noticeEnding)', 'CGRectZero)'),
                              ('waitForExpectations:@[openedOutside] timeout:10', 'waitForExpectations:@[openedOutside] timeout:11'),
                              ('case XCUIApplicationStateUnknown: return @"unknown";', 'case XCUIApplicationStateUnknown: return @"foreground";')]:
            with self.subTest(mutation=before), self.assertRaises(ValueError):
                restore_phone_for_historical_observer(self.phone.replace(before, after, 1))
        outside = self.phone.replace('XCTAssertFalse(self.app.staticTexts[@"scan.result"].exists);',
                                    'XCTAssertTrue(self.app.staticTexts[@"scan.result"].exists);', 1)
        self.assertNotEqual(hashlib.sha256(restore_phone_for_historical_observer(outside).encode()).hexdigest(), 'e29e743721b4a539550cd1d563b0ec1834a368b1f2056cbc9a4c307202202648')

    def test_historical_unit_normalizer_keeps_the_original_inventory_and_unrelated_assertions(self):
        restored = restore_unit_for_historical_observer(self.unit)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(), '9c48f6dac92deff8383127febef1e302f4b9315ea184c2b6adcdf80ab3f63612')
        for before, after in [('notice.bounds.size.height, completeNotice.height', 'notice.bounds.size.height + 100, completeNotice.height'),
                              ('constraint.multiplier, 0.45', 'constraint.multiplier, 0.95'),
                              ('constraint.firstItem == actions', 'constraint.firstItem == notice'),
                              ('constraint.secondItem == privacy.view.safeAreaLayoutGuide', 'constraint.secondItem == privacy.view'),
                              ('constraint.relation == NSLayoutRelationLessThanOrEqual', 'constraint.relation == NSLayoutRelationEqual'),
                              ('CGRectContainsRect(actions.bounds, originalTarget)', 'YES'),
                              ('ForCategory:UIContentSizeCategoryLarge];', 'ForCategory:UIContentSizeCategorySmall];')]:
            with self.subTest(mutation=before), self.assertRaises(ValueError):
                restore_unit_for_historical_observer(self.unit.replace(before, after, 1))
        outside = self.unit.replace('XCTAssertNil([QRCodeCodec imageForPayload:@""]);', 'XCTAssertNotNil([QRCodeCodec imageForPayload:@""]);', 1)
        self.assertNotEqual(hashlib.sha256(restore_unit_for_historical_observer(outside).encode()).hexdigest(), '9c48f6dac92deff8383127febef1e302f4b9315ea184c2b6adcdf80ab3f63612')

    def test_share_system_observation_is_once_scoped_bounded_and_never_supplies_readiness(self):
        helper = method(self.pad, 'retainSpringboardShareObservation')
        for token in ('if (self.shareSystemObservationAttempted) return;', 'self.shareSystemObservationAttempted = YES;',
                      'initWithBundleIdentifier:@"com.apple.springboard"', 'system.otherElements matchingIdentifier:@"ActivityListView"',
                      'activityCount != 1', 'label == %@", @"Native iPad QR result 你好"',
                      'activity.cells matchingIdentifier:@"actionGroupCell"', 'XCUIElementTypeStaticText, @"cellTitleLabel", @"Copy"',
                      'elapsed < 10', 'data.length <= 3072',
                      '@"observations_qualify_pass": [NSNumber numberWithBool:NO]'):
            self.assertIn(token, helper)
        for getter in ('activities.count', 'activity.frame', 'payloads.count', 'payloads.firstMatch.frame',
                       'copies.count', 'copy.enabled', 'copy.hittable', 'copy.frame'):
            self.assertEqual(helper.count(getter), 1, getter)
        for token in ('debugDescription', '[system launch]', '[system activate]', '[system terminate]', ' tap]', 'swipe', 'sleep', 'com.apple.UIKit'):
            self.assertNotIn(token, helper)
        case = test_methods(self.pad)['testSplitSelectionRotationAndAnchoredShare']
        diagnostic = 'if (readiness != XCTWaiterResultCompleted) [self retainSpringboardShareObservation];'
        self.assertEqual(case.count(diagnostic), 1)
        self.assertLess(case.index('XCTWaiterResult readiness ='), case.index(diagnostic))
        self.assertLess(case.index(diagnostic), case.index('XCTAssertEqual(readiness,'))
        predicate = case[case.index('NSPredicate *shareReady ='):case.index('// Start at the original point;')]
        self.assertNotIn('Springboard', predicate)
        late = method(self.pad, 'tearDown').split('    [self retainShareReadinessTrace];', 1)[0]
        self.assertIn('if (self.shareSystemObservationLate)', late)
        self.assertIn('return;', late)
        for token in ('debugDescription', 'capture:', '[self.app terminate]', 'orientation =', 'observeStartupValueOnce'):
            self.assertNotIn(token, late)

    def test_historical_pad_normalization_rejects_changed_new_system_observer(self):
        old = restore_pad_for_historical_observer(self.pad)
        self.assertEqual(hashlib.sha256(old.encode()).hexdigest(), PAD_BASE_SHA256)
        for before, after in [('elapsed < 10', 'elapsed < 100'),
                              ('activityCount != 1', 'activityCount > 1'),
                              ('data.length <= 3072', 'data.length <= 40960'),
                              ('self.shareSystemObservationAttempted = YES;', 'self.shareSystemObservationAttempted = NO;')]:
            with self.subTest(mutation=before), self.assertRaises(ValueError):
                restore_pad_for_historical_observer(self.pad.replace(before, after, 1))

    def test_historical_pad_input_is_exact_and_new_privacy_block_cannot_hide_other_changes(self):
        restored = restore_pad_for_historical_observer(self.pad)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(), PAD_BASE_SHA256)
        for before, after in [('issueHandler:nil error:&policyError', 'issueHandler:nil error:NULL'),
                              ('policyBeginning));', 'CGRectZero));')]:
            with self.subTest(mutation=before), self.assertRaises(ValueError):
                restore_pad_for_historical_observer(self.pad.replace(before, after, 1))
        with self.assertRaises(ValueError):
            restore_pad_for_historical_observer(self.pad+self.pad[self.pad.index(PAD_START):])
        outside = self.pad.replace('self.app.tables[@"history.table"].cells.count, 1',
                                   'self.app.tables[@"history.table"].cells.count, 0', 1)
        self.assertNotEqual(hashlib.sha256(restore_pad_for_historical_observer(outside).encode()).hexdigest(), PAD_BASE_SHA256)


if __name__ == '__main__':
    unittest.main()
