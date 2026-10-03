#import <UIKit/UIKit.h>
#import "QRHistoryStore.h"
@interface AppDelegate : UIResponder <UIApplicationDelegate>
@property (nonatomic, strong) QRHistoryStore *historyStore;
@property (nonatomic, readonly) NSManagedObjectContext *managedObjectContext;
+ (AppDelegate *)appDelegate;
- (void)saveContext;
- (NSURL *)applicationDocumentsDirectory;
@end
