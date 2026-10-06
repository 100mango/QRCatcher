#import <UIKit/UIKit.h>
#import "QRHistoryStore.h"
@interface AppDelegate : UIResponder <UIApplicationDelegate>
@property (nonatomic, strong) QRHistoryStore *historyStore;
@property (nonatomic, readonly) NSManagedObjectContext *managedObjectContext;
+ (AppDelegate *)appDelegate;
- (void)saveContext;
- (NSURL *)applicationDocumentsDirectory;
@end

#if DEBUG
// Closed, finite startup slice. These symbols and call sites are absent in Release.
typedef NS_ENUM(NSUInteger, QRStartupPhase) {
    QRStartupMainEntry, QRStartupStoreEnter, QRStartupStoreReturn,
    QRStartupWatchEnter, QRStartupWatchReturn, QRStartupDelegateReturn,
    QRStartupFixtureEncodeEnter, QRStartupFixtureEncodeReturn,
    QRStartupFixtureDecodeEnter, QRStartupFixtureDecodeReturn,
    QRStartupFixtureHandleSaveEnter, QRStartupFixtureHandleSaveReturn,
    QRStartupMainQueueTurn, QRStartupPhaseCount
};
void QRStartupObservationBegin(double entryWall);
void QRStartupObservationMark(QRStartupPhase phase);
void QRStartupObservationAttach(UILabel *label);
NSString *QRStartupObservationMergeCameraValue(NSString *cameraValue);
void QRStartupObservationScheduleMainQueueTurn(void);
#endif
