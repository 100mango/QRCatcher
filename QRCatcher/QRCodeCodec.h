#import <UIKit/UIKit.h>
NS_ASSUME_NONNULL_BEGIN
@interface QRCodeCodec : NSObject
+ (nullable UIImage *)imageForPayload:(NSString *)payload;
+ (NSArray<NSString *> *)payloadsInImage:(UIImage *)image;
@end
NS_ASSUME_NONNULL_END
