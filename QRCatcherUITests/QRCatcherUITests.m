#import <XCTest/XCTest.h>
#import <UIKit/UIKit.h>
#import "QRUIInterruptionSafety.h"
@interface QRCatcherUITests : XCTestCase
@property (nonatomic, strong) XCUIApplication *app;
@property (nonatomic, strong) id interruptionGuard;
@property (nonatomic, strong) id cameraMonitor;
- (void)assertChineseHistoryResultKeepsCompletePayloadAndRepeatedCancel;
- (void)assertOfflinePrivacyForChinese:(BOOL)Chinese;
@end
@implementation QRCatcherUITests
+ (void)load { NSLog(@"QRCatcher UI regression bundle loaded"); }
- (void)setUp {
    [super setUp]; self.continueAfterFailure = NO;
    self.interruptionGuard = QRInstallFailClosedInterruptionMonitor(self);
    self.app = [XCUIApplication new];
}
- (void)tearDown {
    if (self.testRun.failureCount > 0) {
        NSString *description = self.app.debugDescription;
        XCUIElement *visibleStatus = self.app.staticTexts[@"scan.status"];
        NSLog(@"PHONE_FAILURE_STATE:%lu STATUS:%@ CAMERA_TRACE:%@", (unsigned long)self.app.state, visibleStatus.exists ? visibleStatus.label : @"status not in visible hierarchy", visibleStatus.exists ? visibleStatus.value : @"no visible diagnostic");
        NSLog(@"PHONE_FAILURE_UI:%@", [description substringToIndex:MIN(description.length, 24000)]);
        XCUIApplication *system = [[XCUIApplication alloc] initWithBundleIdentifier:@"com.apple.springboard"];
        XCUIElement *cameraAlert = [system.alerts containingPredicate:[NSPredicate predicateWithFormat:@"label CONTAINS %@ AND label CONTAINS %@", @"QRCatcher", @"camera"]].firstMatch;
        if (cameraAlert.exists) NSLog(@"PHONE_FAILURE_CAMERA_DIALOG:%@", cameraAlert.debugDescription);
        [self logSyntheticScreenshot:@"phone-failure"];
    }
    [self.app terminate];
    XCUIDevice.sharedDevice.orientation = UIDeviceOrientationPortrait; [super tearDown];
    if (self.cameraMonitor) [self removeUIInterruptionMonitor:self.cameraMonitor];
    [self removeUIInterruptionMonitor:self.interruptionGuard];
}
- (void)launch:(NSArray *)arguments { self.app.launchArguments = [@[@"-ui-testing", @"-AppleLanguages", @"(en)", @"-AppleLocale", @"en_US"] arrayByAddingObjectsFromArray:arguments]; [self.app launch]; }
- (void)logSyntheticScreenshot:(NSString *)name {
    NSData *JPEG = UIImageJPEGRepresentation(XCUIScreen.mainScreen.screenshot.image, 0.55);
    XCTAssertLessThanOrEqual(JPEG.length, 500 * 1024);
    if (JPEG.length > 500 * 1024) return;
    XCTAttachment *attachment = [XCTAttachment attachmentWithData:JPEG uniformTypeIdentifier:@"public.jpeg"];
    attachment.name = name;
    attachment.lifetime = XCTAttachmentLifetimeKeepAlways;
    [self addAttachment:attachment];
    // The workflow exports/streams named attachments after XCTest finishes.
    // Console transport must not consume the app's execution-time allowance.
}
- (void)assertOfflinePrivacyForChinese:(BOOL)Chinese {
    XCUIElementQuery *bodies = [self.app.staticTexts matchingIdentifier:@"privacy.body"];
    XCUIElement *body = bodies.firstMatch;
    XCTAssertTrue([body waitForExistenceWithTimeout:5]);
    XCTAssertEqual(bodies.count, 1);
    NSString *approved = Chinese ? @"Celluloid、QRCatcher 和 TouchColor 在设备本地处理照片、相机画面、二维码或颜色数据，开发者不收集或上传这些数据。用户主动分享、打开链接，以及系统 iCloud 同步等行为由相应服务处理。如有隐私问题，请联系 100mango@gmail.com。本地数据可通过相应应用或系统删除，权限可在系统设置中撤回。" : @"Celluloid, QRCatcher, and TouchColor process photos, camera images, QR codes, or color data locally on your device. The developer does not collect or upload this data. Actions you choose to take, such as sharing or opening links, and system services such as iCloud sync are handled by the respective services. For privacy questions, contact 100mango@gmail.com. Local data can be deleted through the relevant app or system, and permissions can be revoked in system settings.";
    XCTAssertEqualObjects(body.label, approved);
    XCTAssertEqual(self.app.webViews.count, 0, @"The default local policy must not create a web document.");
    XCTAssertEqual(self.app.state, XCUIApplicationStateRunningForeground);
    XCUIElement *content = self.app.scrollViews[@"privacy.content"];
    XCUIElement *actions = self.app.scrollViews[@"privacy.actionScroll"];
    CGRect viewport = CGRectIntersection(self.app.frame, content.frame);
    XCTAssertFalse(CGRectIsEmpty(viewport));
    XCTAssertGreaterThan(CGRectGetHeight(body.frame), 0);
    XCTAssertGreaterThan(CGRectGetWidth(body.frame), 0);
    XCTAssertGreaterThanOrEqual(CGRectGetMinX(body.frame), CGRectGetMinX(viewport));
    XCTAssertLessThanOrEqual(CGRectGetMaxX(body.frame), CGRectGetMaxX(viewport));
    CGRect beginning = CGRectMake(CGRectGetMinX(body.frame), CGRectGetMinY(body.frame), CGRectGetWidth(body.frame), MIN(20, CGRectGetHeight(body.frame)));
    XCTAssertTrue(CGRectContainsRect(viewport, beginning), @"The approved text must begin visibly in the real scroll pane.");
    XCUIElement *external = self.app.buttons[@"privacy.externalPolicy"];
    XCTAssertEqualObjects(external.label, Chinese ? @"在浏览器打开" : @"Open in Browser");
    for (NSUInteger attempt = 0; attempt < 2; attempt++) {
        if (external.hittable && CGRectContainsRect(actions.frame, external.frame)) break;
        [actions swipeUp];
    }
    XCTAssertTrue(external.hittable);
    XCTAssertTrue(CGRectContainsRect(actions.frame, external.frame));
    XCTAssertTrue(CGRectContainsRect(viewport, beginning), @"Action scrolling must preserve the visible local text.");
    XCTAssertTrue(self.app.navigationBars.buttons[@"privacy.close"].hittable);
    NSError *error = nil;
    XCTAssertTrue([self.app performAccessibilityAuditWithAuditTypes:XCUIAccessibilityAuditTypeAll issueHandler:nil error:&error], @"Offline privacy accessibility audit: %@", error);
}
- (void)testProductionCameraAllowThenResetAndDeny {
    self.app.launchArguments = @[@"-AppleLanguages", @"(en)", @"-AppleLocale", @"en_US"];
    [self.app resetAuthorizationStatusForResource:XCUIProtectedResourceCamera];
    __block BOOL handledAllow = NO;
    id allowMonitor = [self addUIInterruptionMonitorWithDescription:@"Allow camera" handler:^BOOL(XCUIElement *alert) {
        QRRespondToObservedCameraPrompt(alert, @"Allow");
        handledAllow = YES; return YES;
    }];
    [self.app launch];
    // A single app tap cannot invoke the monitor before the real dialog exists.
    // Observe only the known SpringBoard camera prompt; polling never taps.
    XCUIApplication *cameraSystem = [[XCUIApplication alloc] initWithBundleIdentifier:@"com.apple.springboard"];
    NSPredicate *cameraPromptReady = [NSPredicate predicateWithBlock:^BOOL(id object, NSDictionary *bindings) {
        (void)object; (void)bindings;
        XCUIElementQuery *dialogs = [cameraSystem.alerts matchingPredicate:[NSPredicate predicateWithFormat:@"label == %@", @"Allow “QRCatcher” to access your camera?"]];
        if (dialogs.count != 1) return NO;
        XCUIElement *dialog = dialogs.firstMatch;
        XCUIElementQuery *buttons = dialog.buttons;
        XCUIElementQuery *allow = [buttons matchingPredicate:[NSPredicate predicateWithFormat:@"label == %@", @"Allow"]];
        XCUIElementQuery *deny = [buttons matchingPredicate:[NSPredicate predicateWithFormat:@"label == %@", @"Don’t Allow"]];
        return buttons.count == 2 && allow.count == 1 && deny.count == 1 &&
               allow.firstMatch.enabled && allow.firstMatch.hittable &&
               deny.firstMatch.enabled && deny.firstMatch.hittable;
    }];
    NSTimeInterval promptStarted = NSProcessInfo.processInfo.systemUptime;
    XCTNSPredicateExpectation *cameraPrompt = [[XCTNSPredicateExpectation alloc] initWithPredicate:cameraPromptReady object:cameraSystem];
    XCTWaiterResult promptResult = [XCTWaiter waitForExpectations:@[cameraPrompt] timeout:10];
    NSLog(@"PRODUCTION_CAMERA_PROMPT_READY outcome=%ld elapsed=%.3f", (long)promptResult,
          NSProcessInfo.processInfo.systemUptime - promptStarted);
    XCTAssertEqual(promptResult, XCTWaiterResultCompleted, @"The exact camera dialog must be ready before the single Allow interaction.");
    if (promptResult != XCTWaiterResultCompleted) return;
    [self.app tap];
    NSPredicate *unavailable = [NSPredicate predicateWithFormat:@"label CONTAINS %@", @"No camera is available"];
    [self expectationForPredicate:unavailable evaluatedWithObject:self.app.staticTexts[@"scan.status"] handler:nil];
    [self waitForExpectationsWithTimeout:10 handler:nil];
    XCTAssertTrue(handledAllow, @"This must exercise the real system Allow dialog, not a launch argument.");
    XCTAssertFalse(self.app.buttons[@"scan.settings"].exists);
    NSLog(@"PRODUCTION_CAMERA_ALLOW_OBSERVED: real system Allow, no simulator capture device");
    [XCUIDevice.sharedDevice pressButton:XCUIDeviceButtonHome]; [self.app activate];
    // Resume schedules real camera configuration on sessionQueue, then publishes
    // the unavailable state back on main. Activation is not that completion.
    XCUIElement *resumedStatus = self.app.staticTexts[@"scan.status"];
    NSTimeInterval resumeStarted = NSProcessInfo.processInfo.systemUptime;
    XCTNSPredicateExpectation *resumedUnavailable = [[XCTNSPredicateExpectation alloc] initWithPredicate:unavailable object:resumedStatus];
    XCTWaiterResult resumedResult = [XCTWaiter waitForExpectations:@[resumedUnavailable] timeout:10];
    NSLog(@"PRODUCTION_CAMERA_RESUMED_WAIT outcome=%ld elapsed=%.3f", (long)resumedResult,
          NSProcessInfo.processInfo.systemUptime - resumeStarted);
    XCTAssertEqual(resumedResult, XCTWaiterResultCompleted, @"The real post-activation unavailable state must settle before permission reset.");
    if (resumedResult != XCTWaiterResultCompleted) return;
    NSString *resumedLabel = resumedStatus.label;
    NSLog(@"PRODUCTION_CAMERA_RESUMED_STATE status=%@", resumedLabel);
    XCTAssertTrue([resumedLabel containsString:@"No camera is available"]);
    [self.app terminate];
    XCTAssertTrue([self.app waitForState:XCUIApplicationStateNotRunning timeout:5]);
    [self removeUIInterruptionMonitor:allowMonitor];
    [self.app resetAuthorizationStatusForResource:XCUIProtectedResourceCamera];
    __block BOOL handledDeny = NO;
    id denyMonitor = [self addUIInterruptionMonitorWithDescription:@"Deny camera after reset" handler:^BOOL(XCUIElement *alert) {
        QRRespondToObservedCameraPrompt(alert, @"Don’t Allow");
        handledDeny = YES; return YES;
    }];
    [self.app launch]; [self.app tap];
    XCTAssertTrue([self.app.buttons[@"scan.settings"] waitForExistenceWithTimeout:10]);
    XCTAssertTrue(handledDeny);
    XCTAssertTrue([self.app.staticTexts[@"scan.status"].label containsString:@"Camera access is off"]);
    NSLog(@"PRODUCTION_CAMERA_DENY_OBSERVED: real system Deny after protected-resource reset");
    [self removeUIInterruptionMonitor:denyMonitor];
}
- (void)testProductionSceneLaunchWithoutCameraStub {
    self.app.launchArguments = @[@"-AppleLanguages", @"(en)", @"-AppleLocale", @"en_US"];
    self.cameraMonitor = [self addUIInterruptionMonitorWithDescription:@"Deny only the observed QRCatcher camera request" handler:^BOOL(XCUIElement *alert) {
        QRRespondToObservedCameraPrompt(alert, @"Don’t Allow");
        return YES;
    }];
    [self.app launch];
    XCTAssertTrue([self.app.tabBars.buttons[@"history.tab"] waitForExistenceWithTimeout:10]);
    NSLog(@"PRODUCTION_VIEWPORT:%@", NSStringFromCGRect(self.app.frame));
    [self.app tap];
    XCUIElement *status = self.app.staticTexts[@"scan.status"];
    NSPredicate *cameraSettled = [NSPredicate predicateWithFormat:@"label CONTAINS %@ OR label CONTAINS %@", @"Camera access is off", @"No camera is available"];
    [self expectationForPredicate:cameraSettled evaluatedWithObject:status handler:nil];
    [self waitForExpectationsWithTimeout:10 handler:nil];
    NSString *cameraStatus = status.label;
    NSLog(@"PRODUCTION_CAMERA_STATE:%@", cameraStatus);
    [self.app.tabBars.buttons[@"history.tab"] tap];
    XCTAssertTrue([self.app.tables[@"history.table"] waitForExistenceWithTimeout:5]);
    [XCUIDevice.sharedDevice pressButton:XCUIDeviceButtonHome]; [self.app activate];
    XCTAssertTrue([self.app.tabBars.buttons[@"scan.tab"] waitForExistenceWithTimeout:5]);
    [self.app.tabBars.buttons[@"scan.tab"] tap];
    XCTAssertEqualObjects(status.label, cameraStatus);
    // The shipped application is portrait-only, including when the device rotates.
    XCUIDevice.sharedDevice.orientation = UIDeviceOrientationLandscapeLeft;
    XCTAssertGreaterThan(CGRectGetHeight(self.app.frame), CGRectGetWidth(self.app.frame));
    XCTAssertTrue(self.app.navigationBars.buttons[@"privacy.policy"].hittable);
    XCUIDevice.sharedDevice.orientation = UIDeviceOrientationPortrait;
}
- (void)testDeniedCameraAndEmptyHistory {
    [self launch:@[@"-reset-history", @"-camera-denied"]];
    XCTAssertTrue([self.app.buttons[@"scan.settings"] waitForExistenceWithTimeout:10]);
    XCTAssertTrue([self.app.staticTexts[@"scan.status"].label containsString:@"Camera access is off"]);
    XCUIElement *privacy = self.app.navigationBars.buttons[@"privacy.policy"];
    XCTAssertTrue(privacy.hittable);
    XCTAssertEqualObjects(privacy.label, @"Privacy Policy");
    [privacy tap];
    XCUIElement *done = self.app.navigationBars.buttons[@"privacy.close"];
    XCTAssertTrue([done waitForExistenceWithTimeout:15]);
    [self assertOfflinePrivacyForChinese:NO];
    NSLog(@"PRIVACY_OPEN_UI:%@", self.app.debugDescription);
    [self logSyntheticScreenshot:@"privacy-open-diagnostic"];
    [self.app.buttons[@"privacy.externalPolicy"] tap];
    XCUIApplication *browser = [[XCUIApplication alloc] initWithBundleIdentifier:@"com.apple.mobilesafari"];
    NSPredicate *browserForeground = [NSPredicate predicateWithBlock:^BOOL(id object, NSDictionary *bindings) {
        (void)object; (void)bindings;
        return browser.state == XCUIApplicationStateRunningForeground &&
            (self.app.state == XCUIApplicationStateRunningBackground || self.app.state == XCUIApplicationStateRunningBackgroundSuspended);
    }];
    XCTNSPredicateExpectation *openedOutside = [[XCTNSPredicateExpectation alloc] initWithPredicate:browserForeground object:browser];
    XCTAssertEqual([XCTWaiter waitForExpectations:@[openedOutside] timeout:10], XCTWaiterResultCompleted, @"Only the explicit policy button opens an external browser.");
    [self.app activate];
    XCTAssertTrue([done waitForExistenceWithTimeout:10]);
    [self assertOfflinePrivacyForChinese:NO];
    [done tap];
    BOOL returnedToScanner = [self.app.buttons[@"scan.settings"] waitForExistenceWithTimeout:5];
    if (!returnedToScanner) {
        NSLog(@"PRIVACY_RETURN_UI:%@", self.app.debugDescription);
        [self logSyntheticScreenshot:@"privacy-return-diagnostic"];
    }
    XCTAssertTrue(returnedToScanner);
    [self.app.tabBars.buttons[@"history.tab"] tap];
    XCTAssertTrue([self.app.staticTexts[@"history.empty"] waitForExistenceWithTimeout:5]);
    XCTAssertTrue(self.app.navigationBars.buttons[@"privacy.policy"].hittable);
    [self.app.tabBars.buttons[@"scan.tab"] tap];
    XCTAssertTrue(self.app.buttons[@"scan.settings"].exists);
}
- (void)testScannedTextPersistsAcrossRelaunchAndBackground {
    // Keep a bounded allowance for this case's two complete app relaunches.
    // Bulk JPEG transfer now happens after the suite, outside app timing.
    self.executionTimeAllowance = 180;
    NSString *payload = @"QRCatcher regression text";
    [self launch:@[@"-reset-history", @"-fixture-payload", payload]];
    XCTAssertTrue([self.app.staticTexts[@"scan.result"] waitForExistenceWithTimeout:10]);
    XCTAssertEqualObjects(self.app.staticTexts[@"scan.result"].label, payload);
    [self logSyntheticScreenshot:@"synthetic-scan-result"];
    XCTAssertFalse(self.app.buttons[@"scan.open"].exists);
    [self.app.tabBars.buttons[@"history.tab"] tap];
    XCTAssertTrue([self.app.tables.cells.staticTexts[payload] waitForExistenceWithTimeout:5]);
    [self logSyntheticScreenshot:@"synthetic-history"];
    [XCUIDevice.sharedDevice pressButton:XCUIDeviceButtonHome]; [self.app activate];
    XCTAssertTrue([self.app.tables.cells.staticTexts[payload] waitForExistenceWithTimeout:5]);
    [self.app terminate]; [self launch:@[]];
    [self.app.tabBars.buttons[@"history.tab"] tap];
    XCTAssertTrue([self.app.tables.cells.staticTexts[payload] waitForExistenceWithTimeout:5]);
    [self.app.tables.cells.staticTexts[payload] tap];
    XCTAssertTrue(self.app.buttons[@"history.result.copy"].exists);
    [self.app.buttons[@"history.result.cancel"] tap];
    [self.app.tables.cells.firstMatch swipeLeft];
    [self.app.buttons[@"Delete"] tap];
    XCTAssertTrue([self.app.staticTexts[@"history.empty"] waitForExistenceWithTimeout:5]);
    [self.app terminate]; [self launch:@[]];
    [self.app.tabBars.buttons[@"history.tab"] tap];
    XCTAssertTrue([self.app.staticTexts[@"history.empty"] waitForExistenceWithTimeout:5]);
}
- (void)testUnreadableResultOffersRetryWithoutSaving {
    [self launch:@[@"-reset-history", @"-fixture-empty"]];
    XCTAssertTrue([self.app.buttons[@"scan.again"] waitForExistenceWithTimeout:10]);
    XCTAssertTrue([self.app.staticTexts[@"scan.status"].label containsString:@"empty or could not be read"]);
    [self.app.tabBars.buttons[@"history.tab"] tap];
    XCTAssertTrue([self.app.staticTexts[@"history.empty"] waitForExistenceWithTimeout:5]);
}
- (void)testWebsiteRequiresExplicitOpenAndCanScanAgain {
    [self launch:@[@"-reset-history", @"-fixture-payload", @"https://example.com/regression"]];
    XCTAssertTrue([self.app.buttons[@"scan.open"] waitForExistenceWithTimeout:10]);
    XCTAssertEqual(self.app.state, XCUIApplicationStateRunningForeground);
    [self.app.navigationBars.buttons[@"privacy.policy"] tap];
    XCTAssertTrue([self.app.navigationBars.buttons[@"privacy.close"] waitForExistenceWithTimeout:15]);
    [self.app.navigationBars.buttons[@"privacy.close"] tap];
    XCTAssertTrue([self.app.buttons[@"scan.open"] waitForExistenceWithTimeout:5]);
    [self.app swipeUp]; [self.app.buttons[@"scan.again"] tap];
    XCTAssertFalse(self.app.staticTexts[@"scan.result"].exists);
    XCTAssertTrue([self.app.staticTexts[@"scan.status"].label containsString:@"No camera"]);
    [self.app terminate];
    [self assertChineseHistoryResultKeepsCompletePayloadAndRepeatedCancel];
}
- (void)testLargeTextLayoutKeepsControlsReachable {
    [self launch:@[@"-reset-history", @"-UIPreferredContentSizeCategoryName", @"UICTContentSizeCategoryAccessibilityXXXL", @"-fixture-payload", @"Long QR text that must wrap without hiding navigation or losing access to the scan again control."]];
    XCTAssertTrue([self.app.staticTexts[@"scan.result"] waitForExistenceWithTimeout:10]);
    [self.app swipeUp]; [self.app swipeUp];
    XCTAssertTrue(self.app.buttons[@"scan.again"].hittable);
    XCTAssertTrue(self.app.tabBars.buttons[@"history.tab"].hittable);
    [self.app.navigationBars.buttons[@"privacy.policy"] tap];
    XCTAssertTrue([self.app.navigationBars.buttons[@"privacy.close"] waitForExistenceWithTimeout:15]);
    [self assertOfflinePrivacyForChinese:NO];
    [self.app.navigationBars.buttons[@"privacy.close"] tap];
    XCTAssertTrue([self.app.tabBars.buttons[@"history.tab"] waitForExistenceWithTimeout:5]);
    XCTAssertEqualObjects(self.app.buttons[@"scan.copy"].label, @"Copy Result");
    [self.app.tabBars.buttons[@"history.tab"] tap];
    XCUIElement *record = self.app.tables.cells.firstMatch;
    XCTAssertTrue([record waitForExistenceWithTimeout:5]);
    XCTAssertGreaterThan(CGRectGetHeight(record.frame), 70);
    XCTAssertGreaterThanOrEqual(CGRectGetMinX(record.frame), 0);
    XCTAssertLessThanOrEqual(CGRectGetMaxX(record.frame), CGRectGetWidth(self.app.frame));
    [record tap];
    XCTAssertTrue(self.app.buttons[@"history.result.copy"].hittable);
    XCTAssertTrue(self.app.buttons[@"history.result.cancel"].hittable);
    XCUIElement *result = self.app.otherElements[@"history.result"];
    XCUIElement *title = result.staticTexts[@"history.result.title"];
    XCUIElement *body = result.staticTexts[@"history.result.payload"];
    NSString *expectedBody = @"Long QR text that must wrap without hiding navigation or losing access to the scan again control.";
    XCTAssertTrue(title.exists); XCTAssertTrue(body.exists);
    XCTAssertEqualObjects(body.label, expectedBody);
    XCTAssertTrue(CGRectContainsRect(self.app.frame, result.frame));
    NSString *hierarchy = result.debugDescription;
    hierarchy = [hierarchy substringToIndex:MIN(hierarchy.length, 20000)];
    XCTAttachment *tree = [XCTAttachment attachmentWithString:hierarchy];
    tree.name = @"phone-largest-result-hierarchy"; tree.lifetime = XCTAttachmentLifetimeKeepAlways; [self addAttachment:tree];
    XCUIElementQuery *textPanes = [result.scrollViews matchingIdentifier:@"history.result.text-scroll"];
    XCUIElementQuery *actionPanes = [result.scrollViews matchingIdentifier:@"history.result.action-scroll"];
    XCTAssertEqual(textPanes.count, 1); XCTAssertEqual(actionPanes.count, 1);
    XCUIElement *textScroll = textPanes.firstMatch, *actionScroll = actionPanes.firstMatch;
    CGRect textViewport = CGRectIntersection(result.frame, textScroll.frame);
    CGRect actionViewport = CGRectIntersection(result.frame, actionScroll.frame);
    XCTAssertFalse(CGRectIsEmpty(textViewport)); XCTAssertFalse(CGRectIsEmpty(actionViewport));
    XCTAssertTrue(CGRectContainsRect(result.frame, textScroll.frame));
    XCTAssertTrue(CGRectContainsRect(result.frame, actionScroll.frame));
    XCTAssertLessThanOrEqual(CGRectGetMaxY(textViewport), CGRectGetMinY(actionViewport));
    XCTAssertTrue(CGRectContainsRect(textViewport, title.frame));
    XCUIElement *copy = result.buttons[@"history.result.copy"], *cancel = result.buttons[@"history.result.cancel"];
    XCTAssertTrue(copy.hittable && CGRectContainsRect(actionViewport, copy.frame));
    CGFloat endpointHeight = MIN(CGRectGetHeight(title.frame), CGRectGetHeight(body.frame));
    XCTAssertGreaterThan(endpointHeight, 0);
    CGRect beginning = CGRectMake(CGRectGetMinX(body.frame), CGRectGetMinY(body.frame), CGRectGetWidth(body.frame), endpointHeight);
    XCTAssertTrue(CGRectContainsRect(textViewport, beginning));
    BOOL needsScrolling = !CGRectContainsRect(textViewport, body.frame) || !CGRectContainsRect(actionViewport, cancel.frame);
    XCTAttachment *requirement = [XCTAttachment attachmentWithString:(needsScrolling ? @"scrolled" : @"unscrolled")];
    requirement.name = @"phone-largest-result-evidence-requirement"; requirement.lifetime = XCTAttachmentLifetimeKeepAlways; [self addAttachment:requirement];
    if (needsScrolling) {
        [self logSyntheticScreenshot:@"phone-largest-history-result-top"];
        for (NSUInteger attempt = 0; attempt < 8; attempt++) {
            CGRect ending = CGRectMake(CGRectGetMinX(body.frame), CGRectGetMaxY(body.frame) - endpointHeight, CGRectGetWidth(body.frame), endpointHeight);
            if (body.hittable && CGRectContainsRect(textViewport, ending)) break;
            [textScroll swipeUp];
        }
        CGRect ending = CGRectMake(CGRectGetMinX(body.frame), CGRectGetMaxY(body.frame) - endpointHeight, CGRectGetWidth(body.frame), endpointHeight);
        XCTAssertTrue(body.hittable && CGRectContainsRect(textViewport, ending), @"The full payload ending must be scroll-reachable: %@", body.debugDescription);
        for (NSUInteger attempt = 0; attempt < 8; attempt++) {
            if (cancel.hittable && CGRectContainsRect(actionViewport, cancel.frame)) break;
            [actionScroll swipeUp];
        }
        XCTAssertTrue(cancel.hittable && CGRectContainsRect(actionViewport, cancel.frame));
        XCTAssertEqualObjects(body.label, expectedBody);
        ending = CGRectMake(CGRectGetMinX(body.frame), CGRectGetMaxY(body.frame) - endpointHeight, CGRectGetWidth(body.frame), endpointHeight);
        XCTAssertTrue(CGRectContainsRect(textViewport, ending), @"Action scrolling must preserve the separately readable text ending");
        NSLog(@"PHONE_LARGEST_RESULT_ENDPOINTS: TEXT_VIEWPORT:%@ ENDING:%@ ACTION_VIEWPORT:%@ CANCEL:%@", NSStringFromCGRect(textViewport), NSStringFromCGRect(ending), NSStringFromCGRect(actionViewport), NSStringFromCGRect(cancel.frame));
        [self logSyntheticScreenshot:@"phone-largest-history-result-end"];
    } else {
        XCTAssertTrue(CGRectContainsRect(textViewport, body.frame));
        XCTAssertTrue(CGRectContainsRect(actionViewport, cancel.frame));
        [self logSyntheticScreenshot:@"phone-largest-history-result"];
    }
    NSError *error = nil;
    XCTAssertTrue([self.app performAccessibilityAuditWithAuditTypes:XCUIAccessibilityAuditTypeAll issueHandler:nil error:&error], @"Largest app-owned result accessibility audit: %@", error);
    [cancel tap];
    XCTNSPredicateExpectation *dismissed = [[XCTNSPredicateExpectation alloc] initWithPredicate:[NSPredicate predicateWithFormat:@"exists == NO"] object:result];
    XCTAssertEqual([XCTWaiter waitForExpectations:@[dismissed] timeout:5], XCTWaiterResultCompleted);
    XCTAssertEqual(self.app.tables[@"history.table"].cells.count, 1);
}

- (void)testAccessibilityOfResultAndHistory {
    [self launch:@[@"-reset-history", @"-fixture-payload", @"Accessible QR result 你好"]];
    XCTAssertTrue([self.app.staticTexts[@"scan.result"] waitForExistenceWithTimeout:10]);
    XCTAssertEqualObjects(self.app.staticTexts[@"scan.result"].label, @"Accessible QR result 你好");
    NSError *error;
    XCTAssertTrue([self.app performAccessibilityAuditWithAuditTypes:XCUIAccessibilityAuditTypeAll issueHandler:nil error:&error], @"Scanner accessibility audit: %@", error);
    [self.app.tabBars.buttons[@"history.tab"] tap];
    XCTAssertTrue([self.app.tables.cells.firstMatch waitForExistenceWithTimeout:5]);
    error = nil;
    XCTAssertTrue([self.app performAccessibilityAuditWithAuditTypes:XCUIAccessibilityAuditTypeAll issueHandler:nil error:&error], @"History accessibility audit: %@", error);
    [self.app.tables.cells.firstMatch tap];
    XCTAssertTrue([self.app.buttons[@"history.result.copy"] waitForExistenceWithTimeout:5]);
    XCTAssertEqualObjects(self.app.staticTexts[@"history.result.payload"].label, @"Accessible QR result 你好");
    error = nil;
    XCTAssertTrue([self.app performAccessibilityAuditWithAuditTypes:XCUIAccessibilityAuditTypeAll issueHandler:nil error:&error], @"History detail accessibility audit: %@", error);
    [self.app.buttons[@"history.result.cancel"] tap];
}
- (void)assertChineseHistoryResultKeepsCompletePayloadAndRepeatedCancel {
    NSString *payload = @"完整的二维码 👩🏽‍💻 e\u0301 العربية 最后";
    self.app.launchArguments = @[@"-ui-testing", @"-reset-history", @"-AppleLanguages", @"(zh-Hans)", @"-AppleLocale", @"zh_CN", @"-fixture-payload", payload];
    [self.app launch];
    XCTAssertTrue([self.app.staticTexts[@"scan.result"] waitForExistenceWithTimeout:10]);
    XCTAssertEqualObjects(self.app.staticTexts[@"scan.result"].label, payload);
    [self.app.tabBars.buttons[@"history.tab"] tap];
    for (NSUInteger cycle = 0; cycle < 2; cycle++) {
        XCUIElement *record = self.app.tables[@"history.table"].cells.firstMatch;
        XCTAssertTrue([record waitForExistenceWithTimeout:5]);
        XCTAssertEqual(self.app.tables[@"history.table"].cells.count, 1);
        [record tap];
        XCUIElement *result = self.app.otherElements[@"history.result"];
        XCTAssertTrue([result waitForExistenceWithTimeout:5]);
        XCTAssertEqualObjects(result.staticTexts[@"history.result.title"].label, @"二维码");
        XCTAssertEqualObjects(result.staticTexts[@"history.result.payload"].label, payload);
        XCTAssertEqualObjects(result.buttons[@"history.result.copy"].label, @"复制内容");
        XCTAssertFalse(result.buttons[@"history.result.open"].exists);
        XCUIElement *cancel = result.buttons[@"history.result.cancel"];
        XCTAssertEqualObjects(cancel.label, @"取消"); XCTAssertTrue(cancel.hittable);
        [cancel tap];
        XCTNSPredicateExpectation *closed = [[XCTNSPredicateExpectation alloc] initWithPredicate:[NSPredicate predicateWithFormat:@"exists == NO"] object:result];
        XCTAssertEqual([XCTWaiter waitForExpectations:@[closed] timeout:5], XCTWaiterResultCompleted);
        XCTAssertTrue(self.app.tables[@"history.table"].cells.firstMatch.staticTexts[payload].exists);
    }
    [self.app.navigationBars.buttons[@"privacy.policy"] tap];
    XCTAssertTrue([self.app.navigationBars.buttons[@"privacy.close"] waitForExistenceWithTimeout:15]);
    [self assertOfflinePrivacyForChinese:YES];
    [self.app.navigationBars.buttons[@"privacy.close"] tap];
    XCTAssertTrue([self.app.tables[@"history.table"].cells.firstMatch.staticTexts[payload] waitForExistenceWithTimeout:5]);
}
@end
