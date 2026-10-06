#import <UIKit/UIKit.h>
@interface QRPrivacyViewController : UIViewController
/// Idempotent cleanup: called before dismissal and again after its transition completes.
@property (nonatomic, copy) void (^dismissalHandler)(void);
@end

#if DEBUG
// Test-only observation of the existing public UIApplication boundary.
void QRPrivacySystemOpenObservationAttach(UILabel *label);
NSString *QRPrivacySystemOpenObservationMergeCameraValue(NSString *cameraValue);
BOOL QRPrivacySystemOpenObservationLaunchGate(NSArray<NSString *> *arguments, int appPID);
int QRPrivacySystemOpenObservationQualifies(unsigned long requests, unsigned long completions,
                                            int opened, int unknown, double started, double completed);
#endif
