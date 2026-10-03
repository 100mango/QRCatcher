#import "AppDelegate.h"
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
    self.historyStore = [[QRHistoryStore alloc] initWithURL:URL];
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
