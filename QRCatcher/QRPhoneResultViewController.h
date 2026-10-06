#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

/// App-owned history detail. Its payload is an immutable, complete snapshot.
/// The caller opens the validated HTTP(S) URL after native dismissal completes.
@interface QRPhoneResultViewController : UIViewController
@property (nonatomic, copy, readonly) NSString *payload;
- (instancetype)initWithPayload:(NSString *)payload
            openWebsiteHandler:(void (^)(NSURL *URL))openWebsiteHandler NS_DESIGNATED_INITIALIZER;
- (instancetype)initWithNibName:(nullable NSString *)nibName bundle:(nullable NSBundle *)bundle NS_UNAVAILABLE;
- (instancetype)initWithCoder:(NSCoder *)coder NS_UNAVAILABLE;
- (instancetype)init NS_UNAVAILABLE;
@end

NS_ASSUME_NONNULL_END
