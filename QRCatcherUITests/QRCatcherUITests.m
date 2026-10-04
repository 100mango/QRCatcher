#import <XCTest/XCTest.h>
#import <UIKit/UIKit.h>
#import "QRUIInterruptionSafety.h"
@interface QRCatcherUITests : XCTestCase
@property (nonatomic, strong) XCUIApplication *app;
@property (nonatomic, strong) id interruptionGuard;
@property (nonatomic, strong) id cameraMonitor;
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
- (void)testProductionCameraAllowThenResetAndDeny {
    self.app.launchArguments = @[@"-AppleLanguages", @"(en)", @"-AppleLocale", @"en_US"];
    [self.app resetAuthorizationStatusForResource:XCUIProtectedResourceCamera];
    __block BOOL handledAllow = NO;
    id allowMonitor = [self addUIInterruptionMonitorWithDescription:@"Allow camera" handler:^BOOL(XCUIElement *alert) {
        QRRespondToObservedCameraPrompt(alert, @"Allow");
        handledAllow = YES; return YES;
    }];
    [self.app launch]; [self.app tap];
    NSPredicate *unavailable = [NSPredicate predicateWithFormat:@"label CONTAINS %@", @"No camera is available"];
    [self expectationForPredicate:unavailable evaluatedWithObject:self.app.staticTexts[@"scan.status"] handler:nil];
    [self waitForExpectationsWithTimeout:10 handler:nil];
    XCTAssertTrue(handledAllow, @"This must exercise the real system Allow dialog, not a launch argument.");
    XCTAssertFalse(self.app.buttons[@"scan.settings"].exists);
    NSLog(@"PRODUCTION_CAMERA_ALLOW_OBSERVED: real system Allow, no simulator capture device");
    [XCUIDevice.sharedDevice pressButton:XCUIDeviceButtonHome]; [self.app activate];
    XCTAssertTrue([self.app.staticTexts[@"scan.status"].label containsString:@"No camera is available"]);
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
    XCUIElement *policyBody = [self.app.webViews.staticTexts containingPredicate:[NSPredicate predicateWithFormat:@"label CONTAINS %@", @"process photos, camera images"]].firstMatch;
    XCTAssertTrue([policyBody waitForExistenceWithTimeout:25], @"The policy must load its approved body, not merely display a Close button.");
    NSLog(@"PRIVACY_OPEN_UI:%@", self.app.debugDescription);
    [self logSyntheticScreenshot:@"privacy-open-diagnostic"];
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
    XCTAssertTrue(self.app.alerts.buttons[@"Copy Result"].exists);
    [self.app.alerts.buttons[@"Cancel"] tap];
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
}
- (void)testLargeTextLayoutKeepsControlsReachable {
    [self launch:@[@"-reset-history", @"-UIPreferredContentSizeCategoryName", @"UICTContentSizeCategoryAccessibilityXXXL", @"-fixture-payload", @"Long QR text that must wrap without hiding navigation or losing access to the scan again control."]];
    XCTAssertTrue([self.app.staticTexts[@"scan.result"] waitForExistenceWithTimeout:10]);
    [self.app swipeUp]; [self.app swipeUp];
    XCTAssertTrue(self.app.buttons[@"scan.again"].hittable);
    XCTAssertTrue(self.app.tabBars.buttons[@"history.tab"].hittable);
    XCTAssertEqualObjects(self.app.buttons[@"scan.copy"].label, @"Copy Result");
    [self.app.tabBars.buttons[@"history.tab"] tap];
    XCUIElement *record = self.app.tables.cells.firstMatch;
    XCTAssertTrue([record waitForExistenceWithTimeout:5]);
    XCTAssertGreaterThan(CGRectGetHeight(record.frame), 70);
    XCTAssertGreaterThanOrEqual(CGRectGetMinX(record.frame), 0);
    XCTAssertLessThanOrEqual(CGRectGetMaxX(record.frame), CGRectGetWidth(self.app.frame));
    [record tap];
    XCTAssertTrue(self.app.alerts.buttons[@"Copy Result"].hittable);
    XCTAssertTrue(self.app.alerts.buttons[@"Cancel"].hittable);
    XCUIElement *alert = self.app.alerts[@"QR Code"];
    XCUIElement *title = alert.staticTexts[@"QR Code"];
    XCUIElement *body = alert.staticTexts[@"Long QR text that must wrap without hiding navigation or losing access to the scan again control."];
    XCTAssertTrue(title.exists); XCTAssertTrue(body.exists);
    NSLog(@"PHONE_LARGEST_NATIVE_ALERT_RENDERING:%@ TITLE:%@ BODY:%@ COPY:%@ CANCEL:%@", NSStringFromCGRect(alert.frame), NSStringFromCGRect(title.frame), NSStringFromCGRect(body.frame), NSStringFromCGRect(alert.buttons[@"Copy Result"].frame), NSStringFromCGRect(alert.buttons[@"Cancel"].frame));
    XCTAssertTrue(CGRectContainsRect(self.app.frame, alert.frame));
    for (XCUIElement *element in @[title, body, alert.buttons[@"Copy Result"], alert.buttons[@"Cancel"]]) {
        XCTAssertTrue(CGRectContainsRect(alert.frame, element.frame), @"Largest native alert element must be fully framed: %@", element.debugDescription);
    }
    [self logSyntheticScreenshot:@"phone-largest-history-alert"];
    [self.app.alerts.buttons[@"Cancel"] tap];
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
}
@end
