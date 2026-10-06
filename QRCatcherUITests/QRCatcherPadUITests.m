#import <XCTest/XCTest.h>
#import <UIKit/UIKit.h>
#include <math.h>
#if DEBUG
#import <CoreFoundation/CFDate.h>
#endif
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
#if DEBUG
static int QRPadStartupLogAllowance(unsigned long used, int finalEvent) {
    unsigned long remaining = used < 4096 ? 4096 - used : 0;
    // Reserve a fixed final UNKNOWN record, even if the returned app JSON fills
    // its separate 4KiB value allowance. Cap fallback omits wall as UNKNOWN.
    return finalEvent ? (int)remaining : remaining > 384 ? (int)(remaining - 384) : 0;
}
#endif
@interface QRCatcherPadUITests : XCTestCase
@property (nonatomic, strong) XCUIApplication *app;
@property (nonatomic, strong) id interruptionGuard;
@property (nonatomic, strong) NSMutableDictionary *shareReadinessTrace;
@property (nonatomic) BOOL shareTraceRetained;
@property (nonatomic) BOOL shareSystemObservationAttempted;
@property (nonatomic) BOOL shareSystemObservationLate;
#if DEBUG
@property (nonatomic, copy) NSString *startupObservationSlot;
@property (nonatomic, copy) NSString *startupObservationRequestID;
@property (nonatomic) BOOL startupObservationReadAttempted;
@property (nonatomic) NSUInteger startupObservationLogBytes;
#endif
@end
@implementation QRCatcherPadUITests
- (void)setUp {
    [super setUp]; self.continueAfterFailure = NO;
    self.shareReadinessTrace = nil; self.shareTraceRetained = NO;
    self.shareSystemObservationAttempted = NO; self.shareSystemObservationLate = NO;
#if DEBUG
    self.startupObservationSlot = nil; self.startupObservationRequestID = nil;
    self.startupObservationReadAttempted = NO; self.startupObservationLogBytes = 0;
#endif
    self.interruptionGuard = QRInstallFailClosedInterruptionMonitor(self);
    self.app = [XCUIApplication new];
}
- (void)tearDown {
    if (self.shareSystemObservationLate) {
        // A returned late system observation cannot justify another AX read or
        // a test-authored device action. The already-failed case stays failed.
        [super tearDown];
        [self removeUIInterruptionMonitor:self.interruptionGuard];
        return;
    }
    [self retainShareReadinessTrace];
#if DEBUG
    if (self.testRun.failureCount > 0) [self observeStartupValueOnce];
#endif
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
- (void)retainSpringboardShareObservation {
    if (self.shareSystemObservationAttempted) return;
    self.shareSystemObservationAttempted = YES;
    NSTimeInterval started = NSProcessInfo.processInfo.systemUptime;
    NSMutableDictionary *record = [@{@"version": @1, @"scope": @"springboard_unique_ActivityListView",
        @"status": @"UNKNOWN", @"observations_qualify_pass": [NSNumber numberWithBool:NO],
        @"activity_count": NSNull.null, @"activity_frame": NSNull.null,
        @"payload_count": NSNull.null, @"payload_frame": NSNull.null,
        @"copy_count": NSNull.null, @"copy_enabled": NSNull.null,
        @"copy_hittable": NSNull.null, @"copy_frame": NSNull.null} mutableCopy];
    // Each public AX getter may block until the unchanged case/outer timeout.
    // A late return stops this observation and all later test-authored reads.
    BOOL (^timely)(void) = ^BOOL {
        NSTimeInterval elapsed = NSProcessInfo.processInfo.systemUptime - started;
        BOOL valid = isfinite(elapsed) && elapsed >= 0 && elapsed < 10;
        if (!valid) self.shareSystemObservationLate = YES;
        return valid;
    };
    id (^frameValue)(CGRect) = ^id(CGRect frame) {
        return QRPadFiniteNonemptyRect(frame) ? (id)@[@(frame.origin.x), @(frame.origin.y), @(frame.size.width), @(frame.size.height)] : (id)NSNull.null;
    };
    NSLog(@"IPAD_SHARE_SPRINGBOARD_OBSERVATION_ENTER unqualified");
    do {
        XCUIApplication *system = [[XCUIApplication alloc] initWithBundleIdentifier:@"com.apple.springboard"];
        XCUIElementQuery *activities = [system.otherElements matchingIdentifier:@"ActivityListView"];
        if (!timely()) break;
        NSUInteger activityCount = activities.count;
        record[@"activity_count"] = @(activityCount);
        if (!timely() || activityCount != 1) break;
        XCUIElement *activity = activities.firstMatch;
        CGRect activityFrame = activity.frame;
        record[@"activity_frame"] = frameValue(activityFrame);
        if (!timely() || !QRPadFiniteNonemptyRect(activityFrame)) break;
        XCUIElementQuery *payloads = [activity.otherElements matchingPredicate:[NSPredicate predicateWithFormat:@"label == %@", @"Native iPad QR result 你好"]];
        NSUInteger payloadCount = payloads.count;
        record[@"payload_count"] = @(payloadCount);
        if (!timely()) break;
        if (payloadCount == 1) {
            record[@"payload_frame"] = frameValue(payloads.firstMatch.frame);
            if (!timely()) break;
        }
        XCUIElementQuery *copies = [[activity.cells matchingIdentifier:@"actionGroupCell"]
            containingPredicate:[NSPredicate predicateWithFormat:@"elementType == %lu AND identifier == %@ AND label == %@",
                (unsigned long)XCUIElementTypeStaticText, @"cellTitleLabel", @"Copy"]];
        NSUInteger copyCount = copies.count;
        record[@"copy_count"] = @(copyCount);
        if (!timely()) break;
        if (copyCount == 1) {
            XCUIElement *copy = copies.firstMatch;
            record[@"copy_enabled"] = [NSNumber numberWithBool:copy.enabled];
            if (!timely()) break;
            record[@"copy_hittable"] = [NSNumber numberWithBool:copy.hittable];
            if (!timely()) break;
            record[@"copy_frame"] = frameValue(copy.frame);
            if (!timely()) break;
        }
        record[@"status"] = @"scoped_observation_only";
    } while (NO);
    record[@"late_return"] = [NSNumber numberWithBool:self.shareSystemObservationLate];
    NSTimeInterval elapsed = NSProcessInfo.processInfo.systemUptime - started;
    record[@"elapsed"] = isfinite(elapsed) && elapsed >= 0 ? (id)@(elapsed) : (id)NSNull.null;
    NSData *data = [NSJSONSerialization dataWithJSONObject:record options:NSJSONWritingSortedKeys error:nil];
    if (data && data.length <= 3072) {
        NSLog(@"IPAD_SHARE_SPRINGBOARD_OBSERVATION:%@", [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding]);
    } else {
        NSLog(@"IPAD_SHARE_SPRINGBOARD_OBSERVATION:UNKNOWN bounded serialization unavailable");
    }
}
#if DEBUG
// These records use only the existing native layout log. Public AX value may
// block until the unchanged case/outer bound; no per-getter deadline exists.
// An outer-killed launch can leave only launch_enter, or value_read_enter.
- (void)logStartupEvent:(NSString *)event observation:(NSDictionary *)observation {
    if (!self.startupObservationRequestID) return;
    double wall = CFAbsoluteTimeGetCurrent();
    NSMutableDictionary *record = [@{@"version": @1, @"event": event,
        @"request_id": self.startupObservationRequestID, @"slot": self.startupObservationSlot,
        @"wall": isfinite(wall) ? (id)@(wall) : (id)NSNull.null,
        @"clock": @"WALL_CF2001", @"interval_state": @"UNKNOWN",
        @"observations_qualify_pass": [NSNumber numberWithBool:NO]} mutableCopy];
    if (observation) record[@"observation"] = observation;
    BOOL finalEvent = [event isEqualToString:@"value_read_return"];
    NSUInteger allowance = QRPadStartupLogAllowance(self.startupObservationLogBytes, finalEvent);
    NSData *data = [NSJSONSerialization dataWithJSONObject:record options:NSJSONWritingSortedKeys error:nil];
    if (!data || data.length > allowance) {
        if (!finalEvent) return;
        record[@"wall"] = NSNull.null;
        record[@"observation"] = @{@"retrieval": @"UNKNOWN_log_cap", @"startup_record_omitted": [NSNumber numberWithBool:YES]};
        data = [NSJSONSerialization dataWithJSONObject:record options:NSJSONWritingSortedKeys error:nil];
        if (!data || data.length > allowance) return;
    }
    self.startupObservationLogBytes += data.length;
    NSLog(@"IPAD_MINI_STARTUP_OBSERVATION:%@", [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding]);
}
- (void)observeStartupValueOnce {
    if (!self.startupObservationRequestID || self.startupObservationReadAttempted) return;
    // Claim before entering the getter: an exception or existing timeout never
    // causes a retry from failure capture. No exists/hittable/readiness query.
    self.startupObservationReadAttempted = YES;
    [self logStartupEvent:@"value_read_enter" observation:nil];
    id value = nil;
    @try { value = self.app.staticTexts[@"scan.status"].value; }
    @catch (NSException *exception) {
        [self logStartupEvent:@"value_read_return" observation:@{@"retrieval": @"UNKNOWN_getter_exception"}];
        return;
    }
    NSDictionary *observation = @{@"retrieval": @"UNKNOWN_missing_invalid_or_wrong_launch"};
    if ([value isKindOfClass:NSString.class] && [value lengthOfBytesUsingEncoding:NSUTF8StringEncoding] <= 4096) {
        NSRange marker = [value rangeOfString:@" mini_startup_v1="];
        if (marker.location != NSNotFound) {
            NSString *json = [value substringFromIndex:NSMaxRange(marker)];
            id parsed = [NSJSONSerialization JSONObjectWithData:[json dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
            if ([parsed isKindOfClass:NSDictionary.class] &&
                [parsed[@"request_id"] isKindOfClass:NSString.class] &&
                [parsed[@"request_id"] isEqualToString:self.startupObservationRequestID] &&
                [parsed[@"slot"] isKindOfClass:NSString.class] &&
                [parsed[@"slot"] isEqualToString:self.startupObservationSlot] &&
                [parsed[@"launch_id"] isKindOfClass:NSString.class] &&
                [[NSUUID alloc] initWithUUIDString:parsed[@"launch_id"]] != nil &&
                [parsed[@"app_pid"] isKindOfClass:NSNumber.class] && [parsed[@"app_pid"] intValue] > 0 &&
                [parsed[@"events"] isKindOfClass:NSArray.class] && [parsed[@"events"] count] <= 16) {
                observation = @{@"retrieval": @"returned_current_request_wall_only", @"startup": parsed};
            }
        }
    }
    [self logStartupEvent:@"value_read_return" observation:observation];
}
- (void)launchPadWithStartupSlot:(NSString *)slot {
    self.startupObservationSlot = slot;
    self.startupObservationRequestID = nil;
    self.startupObservationReadAttempted = NO; self.startupObservationLogBytes = 0;
    if (slot) {
        self.startupObservationRequestID = NSUUID.UUID.UUIDString;
        self.app.launchArguments = [self.app.launchArguments arrayByAddingObjectsFromArray:@[
            @"-mini-startup-observation-v1", @"-mini-startup-launch-id", self.startupObservationRequestID,
            @"-mini-startup-slot", slot]];
        [self logStartupEvent:@"launch_enter" observation:nil];
    }
    [self.app launch];
    [self logStartupEvent:@"launch_return" observation:nil];
    [self observeStartupValueOnce];
}
#endif
- (void)launchWithArguments:(NSArray *)extra {
    self.app.launchArguments = [@[@"-ui-testing", @"-reset-history", @"-AppleLanguages", @"(en)", @"-AppleLocale", @"en_US", @"-fixture-payload", @"Native iPad QR result 你好"] arrayByAddingObjectsFromArray:extra];
#if DEBUG
    [self launchPadWithStartupSlot:self.startupObservationSlot];
#else
    [self.app launch];
#endif
    XCTAssertTrue([self.app.staticTexts[@"scan.result"] waitForExistenceWithTimeout:15]);
}
- (void)capture:(NSString *)name {
    NSData *data = UIImageJPEGRepresentation(XCUIScreen.mainScreen.screenshot.image, 0.5);
    XCTAssertLessThanOrEqual(data.length, 800 * 1024);
    XCTAttachment *attachment = [XCTAttachment attachmentWithData:data uniformTypeIdentifier:@"public.jpeg"];
    attachment.name = name; attachment.lifetime = XCTAttachmentLifetimeKeepAlways; [self addAttachment:attachment];
}
- (void)testSplitSelectionRotationAndAnchoredShare {
#if DEBUG
    self.startupObservationSlot = @"split-initial";
#endif
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
    if (readiness != XCTWaiterResultCompleted) [self retainSpringboardShareObservation];
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
#if DEBUG
    [self launchPadWithStartupSlot:@"split-reopen"];
#else
    [self.app launch];
#endif
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
#if DEBUG
    self.startupObservationSlot = @"largest-initial";
#endif
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
    XCUIElement *policyBody = self.app.staticTexts[@"privacy.body"];
    XCTAssertTrue([policyBody waitForExistenceWithTimeout:5]);
    NSString *approvedPolicy = @"Celluloid, QRCatcher, and TouchColor process photos, camera images, QR codes, or color data locally on your device. The developer does not collect or upload this data. Actions you choose to take, such as sharing or opening links, and system services such as iCloud sync are handled by the respective services. For privacy questions, contact 100mango@gmail.com. Local data can be deleted through the relevant app or system, and permissions can be revoked in system settings.";
    XCTAssertEqualObjects(policyBody.label, approvedPolicy);
    XCTAssertEqual(self.app.webViews.count, 0);
    XCTAssertEqual(self.app.state, XCUIApplicationStateRunningForeground);
    CGRect policyViewport = CGRectIntersection(self.app.frame, self.app.scrollViews[@"privacy.content"].frame);
    XCTAssertFalse(CGRectIsEmpty(policyViewport));
    XCTAssertGreaterThan(CGRectGetHeight(policyBody.frame), 0);
    XCTAssertGreaterThan(CGRectGetWidth(policyBody.frame), 0);
    XCTAssertGreaterThanOrEqual(CGRectGetMinX(policyBody.frame), CGRectGetMinX(policyViewport));
    XCTAssertLessThanOrEqual(CGRectGetMaxX(policyBody.frame), CGRectGetMaxX(policyViewport));
    CGRect policyBeginning = CGRectMake(CGRectGetMinX(policyBody.frame), CGRectGetMinY(policyBody.frame), CGRectGetWidth(policyBody.frame), MIN(20, CGRectGetHeight(policyBody.frame)));
    XCTAssertTrue(CGRectContainsRect(policyViewport, policyBeginning));
    XCUIElement *externalPolicy = self.app.buttons[@"privacy.externalPolicy"];
    XCUIElement *policyActions = self.app.scrollViews[@"privacy.actionScroll"];
    for (NSUInteger attempt = 0; attempt < 2; attempt++) {
        if (externalPolicy.hittable && CGRectContainsRect(policyActions.frame, externalPolicy.frame)) break;
        [policyActions swipeUp];
    }
    XCTAssertTrue(externalPolicy.hittable);
    XCTAssertTrue(CGRectContainsRect(policyActions.frame, externalPolicy.frame));
    XCTAssertTrue(CGRectContainsRect(policyViewport, policyBeginning));
    NSError *policyError = nil;
    XCTAssertTrue([self.app performAccessibilityAuditWithAuditTypes:XCUIAccessibilityAuditTypeAll issueHandler:nil error:&policyError], @"iPad largest-text offline privacy accessibility audit: %@", policyError);
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
