#import <XCTest/XCTest.h>
#import <UIKit/UIKit.h>
#include <math.h>
#import "QRUIInterruptionSafety.h"
static BOOL QRPadFiniteNonemptyRect(CGRect rect) {
    return isfinite(rect.origin.x) && isfinite(rect.origin.y) && isfinite(rect.size.width) && isfinite(rect.size.height) &&
        rect.size.width > 0 && rect.size.height > 0;
}
@interface QRCatcherPadUITests : XCTestCase
@property (nonatomic, strong) XCUIApplication *app;
@property (nonatomic, strong) id interruptionGuard;
@end
@implementation QRCatcherPadUITests
- (void)setUp {
    [super setUp]; self.continueAfterFailure = NO;
    self.interruptionGuard = QRInstallFailClosedInterruptionMonitor(self);
    self.app = [XCUIApplication new];
}
- (void)tearDown {
    if (self.testRun.failureCount > 0) { NSLog(@"IPAD_FAILURE_UI:%@", self.app.debugDescription); [self capture:@"ipad-failure"]; }
    [self.app terminate]; XCUIDevice.sharedDevice.orientation = UIDeviceOrientationPortrait; [super tearDown];
    [self removeUIInterruptionMonitor:self.interruptionGuard];
}
- (void)launchWithArguments:(NSArray *)extra {
    self.app.launchArguments = [@[@"-ui-testing", @"-reset-history", @"-AppleLanguages", @"(en)", @"-AppleLocale", @"en_US", @"-fixture-payload", @"Native iPad QR result 你好"] arrayByAddingObjectsFromArray:extra];
    [self.app launch];
    XCTAssertTrue([self.app.staticTexts[@"scan.result"] waitForExistenceWithTimeout:15]);
}
- (void)capture:(NSString *)name {
    NSData *data = UIImageJPEGRepresentation(XCUIScreen.mainScreen.screenshot.image, 0.5);
    XCTAssertLessThanOrEqual(data.length, 800 * 1024);
    XCTAttachment *attachment = [XCTAttachment attachmentWithData:data uniformTypeIdentifier:@"public.jpeg"];
    attachment.name = name; attachment.lifetime = XCTAttachmentLifetimeKeepAlways; [self addAttachment:attachment];
}
- (void)testSplitSelectionRotationAndAnchoredShare {
    [self launchWithArguments:@[]];
    XCUIElement *history = self.app.tables[@"history.table"];
    XCTAssertTrue([history waitForExistenceWithTimeout:5]);
    XCTAssertTrue(self.app.staticTexts[@"scan.result"].exists);
    XCTAssertFalse(self.app.tabBars.firstMatch.exists, @"Native iPad must use the split workflow, not the phone tab shell.");
    XCUIDevice.sharedDevice.orientation = UIDeviceOrientationLandscapeLeft;
    NSPredicate *landscape = [NSPredicate predicateWithBlock:^BOOL(id object, NSDictionary *bindings) { XCUIElement *app = object; return app.frame.size.width > app.frame.size.height; }];
    [self expectationForPredicate:landscape evaluatedWithObject:self.app handler:nil]; [self waitForExpectationsWithTimeout:8 handler:nil];
    XCTAssertTrue(history.hittable);
    [history.cells.firstMatch tap];
    XCTAssertEqualObjects(self.app.staticTexts[@"scan.result"].label, @"Native iPad QR result 你好");
    XCTAssertEqual(history.cells.count, 1);
    XCUIElement *share = self.app.buttons[@"scan.share"];
    if (!share.hittable) [self.app.scrollViews.firstMatch swipeUp];
    XCTAssertTrue(share.hittable);
    CGRect anchor = share.frame;
    [share tap];
    // SDK27 exposes Copy as an actionGroupCell in an anchored native popover.
    // Pro ebcc showed this complete UI about9.6s after the tap, beyond the old
    // 5s broad-container wait. Keep one bounded, passive readiness prerequisite.
    XCUIElementQuery *popovers = [self.app.popovers containingType:XCUIElementTypeOther identifier:@"ActivityListView"];
    XCUIElement *popover = popovers.firstMatch;
    XCUIElement *activity = popover.otherElements[@"ActivityListView"];
    XCUIElement *caption = activity.otherElements[@"LP.CaptionBar.BottomCaption"];
    XCUIElement *copy = [activity.cells matchingPredicate:[NSPredicate predicateWithFormat:@"identifier == %@ AND label == %@", @"actionGroupCell", @"Copy"]].firstMatch;
    NSPredicate *shareReady = [NSPredicate predicateWithBlock:^BOOL(id object, NSDictionary *bindings) {
        return popovers.count == 1 && popover.exists && activity.exists && caption.exists &&
            [caption.label isEqualToString:@"Native iPad QR result 你好"] && copy.exists && copy.enabled && copy.hittable;
    }];
    NSTimeInterval readinessStarted = NSProcessInfo.processInfo.systemUptime;
    XCTNSPredicateExpectation *ready = [[XCTNSPredicateExpectation alloc] initWithPredicate:shareReady object:nil];
    XCTWaiterResult readiness = [XCTWaiter waitForExpectations:@[ready] timeout:10];
    NSLog(@"IPAD_NATIVE_SHARE_READINESS outcome=%ld elapsed=%.3f", (long)readiness, NSProcessInfo.processInfo.systemUptime - readinessStarted);
    XCTAssertEqual(readiness, XCTWaiterResultCompleted, @"Expected native share popover, matching payload caption and hittable Copy cell");
    if (readiness != XCTWaiterResultCompleted) return;
    BOOL currentReady = [shareReady evaluateWithObject:nil];
    XCTAssertTrue(currentReady);
    if (!currentReady) return;
    CGRect presented = popover.frame;
    CGRect copyFrame = copy.frame, window = self.app.frame;
    // The app anchors sourceView/sourceRect to Share but does not constrain
    // UIKit's permitted arrow direction. Accept each directionally aligned
    // side, rather than asserting the above-source direction seen on Pro.
    // A wide source control does not require the arrow to target its center.
    BOOL verticalSide = MIN(CGRectGetMaxX(presented), CGRectGetMaxX(anchor)) > MAX(CGRectGetMinX(presented), CGRectGetMinX(anchor)) &&
        (CGRectGetMaxY(presented) <= CGRectGetMinY(anchor) || CGRectGetMinY(presented) >= CGRectGetMaxY(anchor));
    BOOL horizontalSide = MIN(CGRectGetMaxY(presented), CGRectGetMaxY(anchor)) > MAX(CGRectGetMinY(presented), CGRectGetMinY(anchor)) &&
        (CGRectGetMaxX(presented) <= CGRectGetMinX(anchor) || CGRectGetMinX(presented) >= CGRectGetMaxX(anchor));
    BOOL anchored = QRPadFiniteNonemptyRect(window) && QRPadFiniteNonemptyRect(presented) &&
        QRPadFiniteNonemptyRect(anchor) && QRPadFiniteNonemptyRect(copyFrame) &&
        CGRectContainsRect(window, presented) && CGRectContainsRect(window, anchor) &&
        CGRectContainsRect(presented, copyFrame) && (verticalSide || horizontalSide);
    NSLog(@"IPAD_NATIVE_SHARE_GEOMETRY popover=%@ anchor=%@ copy=%@", NSStringFromCGRect(presented), NSStringFromCGRect(anchor), NSStringFromCGRect(copyFrame));
    XCTAssertTrue(anchored, @"The share popover must fit on a source-aligned side and expose the whole Copy cell");
    if (!anchored) return;
    [self capture:@"ipad-anchored-share"];
    // Dismiss the popover by tapping outside it, retaining the selected payload.
    [history.cells.firstMatch tap];
    XCTNSPredicateExpectation *dismissed = [[XCTNSPredicateExpectation alloc] initWithPredicate:[NSPredicate predicateWithFormat:@"exists == NO"] object:popover];
    XCTWaiterResult dismissal = [XCTWaiter waitForExpectations:@[dismissed] timeout:5];
    XCTAssertEqual(dismissal, XCTWaiterResultCompleted);
    if (dismissal != XCTWaiterResultCompleted) return;
    XCTAssertEqualObjects(self.app.staticTexts[@"scan.result"].label, @"Native iPad QR result 你好");
    XCUIDevice.sharedDevice.orientation = UIDeviceOrientationPortrait;
    XCTAssertTrue([self.app.buttons[@"scan.import"] waitForExistenceWithTimeout:5]);
    [self capture:@"ipad-split-portrait"];
    [self.app terminate];
    self.app.launchArguments = @[@"-ui-testing", @"-AppleLanguages", @"(en)"];
    [self.app launch];
    XCTAssertTrue([self.app.tables[@"history.table"].cells.firstMatch waitForExistenceWithTimeout:10]);
    [self.app.tables[@"history.table"].cells.firstMatch tap];
    XCTAssertEqualObjects(self.app.staticTexts[@"scan.result"].label, @"Native iPad QR result 你好");
}
- (void)testRealPhotoImportReplacesSelectionAndPreservesBothRecords {
    [self launchWithArguments:@[]];
    XCUIElement *import = self.app.buttons[@"scan.import"];
    if (!import.hittable) { [self.app.scrollViews.firstMatch swipeUp]; [self.app.scrollViews.firstMatch swipeUp]; }
    XCTAssertTrue(import.hittable); [import tap];
    [self.app.buttons[@"Photo Library"] tap];
    // The iPad picker has a sidebar collection before its actual asset grid.
    // Use the real photo-image AX identifier observed in run 37121579198.
    XCUIElement *photo = self.app.images[@"PXGGridLayout-Info"].firstMatch;
    XCTAssertTrue([photo waitForExistenceWithTimeout:45], @"%@", self.app.debugDescription);
    [photo tap];
    NSPredicate *decoded = [NSPredicate predicateWithFormat:@"label == %@", @"QRCatcher 你好 🌈 123"];
    [self expectationForPredicate:decoded evaluatedWithObject:self.app.staticTexts[@"scan.result"] handler:nil];
    [self waitForExpectationsWithTimeout:20 handler:nil];
    XCTAssertEqual(self.app.tables[@"history.table"].cells.count, 2);
    XCTAssertFalse(self.app.buttons[@"scan.open"].exists);
    [self capture:@"ipad-imported-photo"];
    [self.app terminate]; self.app.launchArguments = @[@"-ui-testing", @"-AppleLanguages", @"(en)"]; [self.app launch];
    XCUIElement *records = self.app.tables[@"history.table"];
    XCTAssertTrue([records.cells.firstMatch waitForExistenceWithTimeout:10]);
    XCTAssertEqual(records.cells.count, 2);
    [records.cells.firstMatch tap];
    XCTAssertEqualObjects(self.app.staticTexts[@"scan.result"].label, @"QRCatcher 你好 🌈 123");
    [self capture:@"ipad-imported-photo"];
}
- (void)testLargeTextImportCancellationAndPrivacyReturn {
    [self launchWithArguments:@[@"-UIPreferredContentSizeCategoryName", @"UICTContentSizeCategoryAccessibilityXXXL"]];
    [self.app.scrollViews.firstMatch swipeUp]; [self.app.scrollViews.firstMatch swipeUp];
    XCTAssertTrue(self.app.buttons[@"scan.import"].hittable);
    [self.app.buttons[@"scan.import"] tap];
    XCTAssertTrue([self.app.buttons[@"Photo Library"] waitForExistenceWithTimeout:5]);
    [self.app.buttons[@"Photo Library"] tap];
    XCUIElement *cancel = self.app.buttons[@"Cancel"].firstMatch;
    XCTAssertTrue([cancel waitForExistenceWithTimeout:10]); [cancel tap];
    XCTAssertEqual(self.app.tables[@"history.table"].cells.count, 1);
    [self.app.navigationBars.buttons[@"privacy.policy"].firstMatch tap];
    XCTAssertTrue([self.app.navigationBars.buttons[@"privacy.close"] waitForExistenceWithTimeout:15]);
    [self.app.navigationBars.buttons[@"privacy.close"] tap];
    XCTAssertTrue([self.app.tables[@"history.table"] waitForExistenceWithTimeout:5]);
    [self capture:@"ipad-large-text"];
    XCUIElement *title = self.app.navigationBars[@"History"].staticTexts[@"History"];
    XCTAssertTrue(title.exists, @"History title remains accessible at largest text");
    XCTAssertEqualObjects(title.label, @"History");
    CGFloat minimumWidth = [@"History" sizeWithAttributes:@{NSFontAttributeName:[UIFont boldSystemFontOfSize:17]}].width;
    XCTAssertGreaterThanOrEqual(title.frame.size.width + 0.5, minimumWidth, @"The visible title must fit, not merely expose a complete AX label");
    NSError *error = nil;
    XCTAssertTrue([self.app performAccessibilityAuditWithAuditTypes:XCUIAccessibilityAuditTypeAll issueHandler:nil error:&error], @"iPad largest-text split/result accessibility audit: %@", error);
}
@end
