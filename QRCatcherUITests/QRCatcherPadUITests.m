#import <XCTest/XCTest.h>
#import <UIKit/UIKit.h>
#include <math.h>
#import "QRUIInterruptionSafety.h"
static BOOL QRPadFiniteNonemptyRect(CGRect rect) {
    return isfinite(rect.origin.x) && isfinite(rect.origin.y) && isfinite(rect.size.width) && isfinite(rect.size.height) &&
        rect.size.width > 0 && rect.size.height > 0;
}
// Observe the existing short-circuit reads exactly once. Missing later reads
// remain unknown; this diagnostic never supplies readiness or hittability.
static BOOL QRPadObserveShareTerm(NSMutableDictionary *attempt, NSString *name,
                                 NSTimeInterval origin, BOOL (^read)(NSMutableDictionary *)) {
    if (!attempt) return read(nil);
    NSMutableDictionary *term = [@{@"state": @"entered", @"started": @(NSProcessInfo.processInfo.systemUptime - origin)} mutableCopy];
    attempt[@"terms"][name] = term; attempt[@"active_term"] = name;
    BOOL result = read(term);
    term[@"state"] = @"completed"; term[@"result"] = @(result);
    term[@"finished"] = @(NSProcessInfo.processInfo.systemUptime - origin);
    attempt[@"active_term"] = NSNull.null;
    return result;
}
@interface QRCatcherPadUITests : XCTestCase
@property (nonatomic, strong) XCUIApplication *app;
@property (nonatomic, strong) id interruptionGuard;
@property (nonatomic, strong) NSMutableDictionary *shareReadinessTrace;
@property (nonatomic) BOOL shareTraceRetained;
@end
@implementation QRCatcherPadUITests
- (void)setUp {
    [super setUp]; self.continueAfterFailure = NO;
    self.shareReadinessTrace = nil; self.shareTraceRetained = NO;
    self.interruptionGuard = QRInstallFailClosedInterruptionMonitor(self);
    self.app = [XCUIApplication new];
}
- (void)tearDown {
    [self retainShareReadinessTrace];
    if (self.testRun.failureCount > 0) { NSLog(@"IPAD_FAILURE_UI:%@", self.app.debugDescription); [self capture:@"ipad-failure"]; }
    [self.app terminate]; XCUIDevice.sharedDevice.orientation = UIDeviceOrientationPortrait; [super tearDown];
    [self removeUIInterruptionMonitor:self.interruptionGuard];
}
- (void)retainShareReadinessTrace {
    if (!self.shareReadinessTrace || self.shareTraceRetained) return;
    self.shareTraceRetained = YES;
    NSError *error = nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:self.shareReadinessTrace options:NSJSONWritingSortedKeys error:&error];
    if (!data || data.length > 4096) {
        NSLog(@"IPAD_SHARE_TRACE_INCOMPLETE encoding_or_cap");
        return;
    }
    NSLog(@"IPAD_SHARE_READINESS_TRACE:%@", [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding]);
    XCTAttachment *attachment = [XCTAttachment attachmentWithData:data uniformTypeIdentifier:@"public.json"];
    attachment.name = @"ipad-share-readiness-trace"; attachment.lifetime = XCTAttachmentLifetimeKeepAlways;
    [self addAttachment:attachment];
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
    // Both retained SDK27 hierarchies have this owned Copy title. The
    // action cell's own label may be empty, so it cannot identify the action.
    XCUIElementQuery *copyCells = [[activity.cells matchingIdentifier:@"actionGroupCell"]
        containingPredicate:[NSPredicate predicateWithFormat:@"elementType == %lu AND identifier == %@ AND label == %@",
            (unsigned long)XCUIElementTypeStaticText, @"cellTitleLabel", @"Copy"]];
    XCUIElement *copy = copyCells.firstMatch;
    NSArray *termOrder = @[@"popover_count", @"popover_exists", @"activity_exists", @"caption_exists", @"caption_matches",
                           @"copy_count", @"copy_exists", @"copy_enabled", @"copy_hittable"];
    NSMutableArray *attempts = [NSMutableArray array];
    NSMutableDictionary *trace = [@{@"version": @1, @"timeout_seconds": @10, @"observations_qualify_pass": @NO,
        @"attempt_count": @0, @"retained_attempt_limit": @2, @"term_order": termOrder, @"attempts": attempts,
        @"waiter_result": NSNull.null, @"wait_elapsed": NSNull.null} mutableCopy];
    self.shareReadinessTrace = trace;
    __block NSTimeInterval readinessStarted = 0;
    __block BOOL observeReadiness = YES;
    NSPredicate *shareReady = [NSPredicate predicateWithBlock:^BOOL(id object, NSDictionary *bindings) {
        NSMutableDictionary *attempt = nil;
        if (observeReadiness) {
            NSUInteger index = [trace[@"attempt_count"] unsignedIntegerValue] + 1;
            trace[@"attempt_count"] = @(index);
            NSMutableDictionary *terms = [NSMutableDictionary dictionary];
            for (NSString *name in termOrder) terms[name] = @{@"state": @"not_evaluated"};
            attempt = [@{@"index": @(index), @"terms": terms, @"active_term": NSNull.null,
                         @"predicate_returned": @NO, @"ready": NSNull.null} mutableCopy];
            [attempts addObject:attempt]; if (attempts.count > 2) [attempts removeObjectAtIndex:0];
        }
        BOOL readyNow =
            QRPadObserveShareTerm(attempt, @"popover_count", readinessStarted, ^BOOL(NSMutableDictionary *term) {
                NSUInteger count = popovers.count; term[@"observed_count"] = @(count); return count == 1;
            }) &&
            QRPadObserveShareTerm(attempt, @"popover_exists", readinessStarted, ^BOOL(NSMutableDictionary *term) { return popover.exists; }) &&
            QRPadObserveShareTerm(attempt, @"activity_exists", readinessStarted, ^BOOL(NSMutableDictionary *term) { return activity.exists; }) &&
            QRPadObserveShareTerm(attempt, @"caption_exists", readinessStarted, ^BOOL(NSMutableDictionary *term) { return caption.exists; }) &&
            QRPadObserveShareTerm(attempt, @"caption_matches", readinessStarted, ^BOOL(NSMutableDictionary *term) {
                NSString *value = caption.label;
                term[@"caption_utf8_bytes"] = value ? @([value lengthOfBytesUsingEncoding:NSUTF8StringEncoding]) : NSNull.null;
                return [value isEqualToString:@"Native iPad QR result 你好"];
            }) &&
            QRPadObserveShareTerm(attempt, @"copy_count", readinessStarted, ^BOOL(NSMutableDictionary *term) {
                NSUInteger count = copyCells.count; term[@"observed_count"] = @(count); return count == 1;
            }) &&
            QRPadObserveShareTerm(attempt, @"copy_exists", readinessStarted, ^BOOL(NSMutableDictionary *term) { return copy.exists; }) &&
            QRPadObserveShareTerm(attempt, @"copy_enabled", readinessStarted, ^BOOL(NSMutableDictionary *term) { return copy.enabled; }) &&
            QRPadObserveShareTerm(attempt, @"copy_hittable", readinessStarted, ^BOOL(NSMutableDictionary *term) { return copy.hittable; });
        attempt[@"predicate_returned"] = @YES; attempt[@"ready"] = @(readyNow);
        return readyNow;
    }];
    // Start at the original point; the native waiter still owns the same10s.
    readinessStarted = NSProcessInfo.processInfo.systemUptime;
    XCTNSPredicateExpectation *ready = [[XCTNSPredicateExpectation alloc] initWithPredicate:shareReady object:nil];
    XCTWaiterResult readiness = [XCTWaiter waitForExpectations:@[ready] timeout:10];
    NSTimeInterval readinessElapsed = NSProcessInfo.processInfo.systemUptime - readinessStarted;
    trace[@"waiter_result"] = @((long)readiness); trace[@"wait_elapsed"] = @(readinessElapsed);
    observeReadiness = NO;
    NSLog(@"IPAD_NATIVE_SHARE_READINESS outcome=%ld elapsed=%.3f", (long)readiness, readinessElapsed);
    [self retainShareReadinessTrace];
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
