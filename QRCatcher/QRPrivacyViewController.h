#import <UIKit/UIKit.h>
@interface QRPrivacyViewController : UIViewController
/// Idempotent cleanup: called before dismissal and again after its transition completes.
@property (nonatomic, copy) void (^dismissalHandler)(void);
@end
