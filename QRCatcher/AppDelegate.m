#import "AppDelegate.h"
#import "QRWatchPhoneService.h"

#if DEBUG
#import <CoreFoundation/CFDate.h>
#include <math.h>

static const NSUInteger QRStartupEventLimit = 16;
static const NSUInteger QRStartupByteLimit = 4096;
static BOOL QRStartupEnabled;
static BOOL QRStartupClockUnknown;
static BOOL QRStartupHasPreviousWall;
static BOOL QRStartupTurnScheduled;
static double QRStartupPreviousWall;
static unsigned long QRStartupSeenPhases;
static NSString *QRStartupRequestID;
static NSString *QRStartupLaunchID;
static NSString *QRStartupSlot;
static NSMutableArray *QRStartupEvents;
static __weak UILabel *QRStartupLabel;
static NSString *QRStartupCameraValue;

// Portable arithmetic policy: wall values correlate records, never prove a
// continuous interval. A forward clock jump is not detectable using wall alone.
static int QRStartupWallComparable(double wall, double previous, int hasPrevious) {
    return isfinite(wall) && (!hasPrevious || (isfinite(previous) && wall >= previous));
}
static int QRStartupCanRecord(unsigned long phase, unsigned long count, unsigned long seen) {
    return phase < 13 && count < 16 && !(seen & (1UL << phase));
}
static int QRStartupLaunchGate(unsigned long uiCount, unsigned long tokenCount,
                               int canonicalUUID, int closedSlot, int appPID) {
    return uiCount == 1 && tokenCount == 1 && canonicalUUID && closedSlot && appPID > 0;
}
static NSUInteger QRStartupArgumentCount(NSArray *args, NSString *flag) {
    NSUInteger count = 0;
    for (NSString *value in args) if ([value isEqualToString:flag]) count += 1;
    return count;
}
static NSString *QRStartupArgumentValue(NSArray *args, NSString *flag) {
    if (QRStartupArgumentCount(args, flag) != 1) return nil;
    NSUInteger index = [args indexOfObject:flag];
    return index + 1 < args.count ? args[index + 1] : nil;
}
static NSString *QRStartupEncodedValue(void) {
    if (!QRStartupEnabled) return QRStartupCameraValue;
    NSDictionary *record = @{@"version": @1, @"request_id": QRStartupRequestID,
        @"launch_id": QRStartupLaunchID, @"slot": QRStartupSlot,
        @"app_pid": @(NSProcessInfo.processInfo.processIdentifier),
        @"clock": @"WALL_CF2001", @"clock_discontinuity": [NSNumber numberWithBool:QRStartupClockUnknown],
        @"interval_state": @"UNKNOWN", @"continuous_responsiveness": [NSNumber numberWithBool:NO],
        @"events": QRStartupEvents, @"event_limit": @(QRStartupEventLimit)};
    NSData *data = [NSJSONSerialization dataWithJSONObject:record options:NSJSONWritingSortedKeys error:nil];
    if (!data || data.length > QRStartupByteLimit) return QRStartupCameraValue;
    NSString *json = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
    NSString *combined = [NSString stringWithFormat:@"%@ mini_startup_v1=%@", QRStartupCameraValue ?: @"", json];
    return [combined lengthOfBytesUsingEncoding:NSUTF8StringEncoding] <= QRStartupByteLimit ? combined : QRStartupCameraValue;
}
static void QRStartupPublish(void) {
    if (QRStartupEnabled && QRStartupLabel) QRStartupLabel.accessibilityValue = QRStartupEncodedValue();
}
static void QRStartupRecord(QRStartupPhase phase, double wall) {
    if (!QRStartupEnabled || !QRStartupCanRecord(phase, QRStartupEvents.count, QRStartupSeenPhases)) return;
    static NSString *const names[] = {@"main_entry", @"store_enter", @"store_return", @"watch_enter", @"watch_return",
        @"delegate_return", @"fixture_encode_enter", @"fixture_encode_return", @"fixture_decode_enter", @"fixture_decode_return",
        @"fixture_handle_save_enter", @"fixture_handle_save_return", @"main_queue_turn"};
    if (!QRStartupWallComparable(wall, QRStartupPreviousWall, QRStartupHasPreviousWall)) QRStartupClockUnknown = YES;
    id timestamp = isfinite(wall) ? (id)@(wall) : (id)NSNull.null;
    [QRStartupEvents addObject:@{@"phase": names[phase], @"wall": timestamp}];
    QRStartupSeenPhases |= 1UL << phase;
    QRStartupPreviousWall = wall; QRStartupHasPreviousWall = YES;
    QRStartupPublish();
}
void QRStartupObservationBegin(double entryWall) {
    NSArray *args = NSProcessInfo.processInfo.arguments;
    NSUInteger uiCount = QRStartupArgumentCount(args, @"-ui-testing");
    NSUInteger tokenCount = QRStartupArgumentCount(args, @"-mini-startup-observation-v1");
    if (uiCount != 1 || tokenCount != 1) return;
    NSString *requestID = QRStartupArgumentValue(args, @"-mini-startup-launch-id");
    NSString *slot = QRStartupArgumentValue(args, @"-mini-startup-slot");
    NSUUID *request = requestID ? [[NSUUID alloc] initWithUUIDString:requestID] : nil;
    BOOL canonicalUUID = request && [request.UUIDString isEqualToString:requestID];
    BOOL closedSlot = slot && [@[@"largest-initial", @"split-initial", @"split-reopen"] containsObject:slot];
    if (!QRStartupLaunchGate(uiCount, tokenCount, canonicalUUID, closedSlot,
                            NSProcessInfo.processInfo.processIdentifier)) return;
    QRStartupRequestID = requestID; QRStartupSlot = slot;
    QRStartupLaunchID = NSUUID.UUID.UUIDString; // Fresh in this process, never an old AX snapshot identity.
    QRStartupEvents = [NSMutableArray arrayWithCapacity:QRStartupEventLimit];
    QRStartupEnabled = YES;
    QRStartupRecord(QRStartupMainEntry, entryWall);
}
void QRStartupObservationMark(QRStartupPhase phase) {
    if (QRStartupEnabled) QRStartupRecord(phase, CFAbsoluteTimeGetCurrent());
}
void QRStartupObservationAttach(UILabel *label) {
    if (!QRStartupEnabled) return;
    QRStartupLabel = label;
    QRStartupPublish();
}
NSString *QRStartupObservationMergeCameraValue(NSString *cameraValue) {
    if (!QRStartupEnabled) return cameraValue;
    QRStartupCameraValue = cameraValue;
    return QRStartupEncodedValue();
}
void QRStartupObservationScheduleMainQueueTurn(void) {
    if (!QRStartupEnabled || QRStartupTurnScheduled) return;
    QRStartupTurnScheduled = YES;
    dispatch_async(dispatch_get_main_queue(), ^{ QRStartupObservationMark(QRStartupMainQueueTurn); });
}
#endif

@implementation AppDelegate
+ (AppDelegate *)appDelegate { return (AppDelegate *)UIApplication.sharedApplication.delegate; }
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)launchOptions {
    NSURL *URL = [[self applicationDocumentsDirectory] URLByAppendingPathComponent:@"coredata.sqlite"];
#if DEBUG
    // UI-test data lives separately from real user history and is never selected in Release.
    if ([NSProcessInfo.processInfo.arguments containsObject:@"-ui-testing"]) {
        URL = [[self applicationDocumentsDirectory] URLByAppendingPathComponent:@"ui-testing.sqlite"];
        if ([NSProcessInfo.processInfo.arguments containsObject:@"-reset-history"]) {
            for (NSString *suffix in @[@"", @"-wal", @"-shm"]) {
                [[NSFileManager defaultManager] removeItemAtPath:[URL.path stringByAppendingString:suffix] error:nil];
            }
        }
    }
#endif
#if DEBUG
    QRStartupObservationMark(QRStartupStoreEnter);
#endif
    self.historyStore = [[QRHistoryStore alloc] initWithURL:URL];
#if DEBUG
    QRStartupObservationMark(QRStartupStoreReturn);
    QRStartupObservationMark(QRStartupWatchEnter);
#endif
    [[QRWatchPhoneService shared] activate];
#if DEBUG
    QRStartupObservationMark(QRStartupWatchReturn);
    QRStartupObservationMark(QRStartupDelegateReturn);
#endif
    return YES;
}
- (NSManagedObjectContext *)managedObjectContext { return self.historyStore.context; }
- (NSURL *)applicationDocumentsDirectory {
    return [[NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask] lastObject];
}
- (void)saveContext {
    NSError *error;
    if (![self.historyStore save:&error]) {
        // Keep the store and pending changes intact. Controllers show actionable storage errors.
        NSLog(@"History save failed: %@", error.localizedDescription);
    }
}
- (void)applicationDidEnterBackground:(UIApplication *)application { [self saveContext]; }
- (void)applicationWillTerminate:(UIApplication *)application { [self saveContext]; }
@end
