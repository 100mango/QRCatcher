#import <Foundation/Foundation.h>
#import <CoreGraphics/CoreGraphics.h>
@class CIImage;
NS_ASSUME_NONNULL_BEGIN
/// UI-independent codec. CGImage uses upright pixels; ImageIO import normalizes EXIF orientation.
@interface QRImageCodec : NSObject
+ (nullable CGImageRef)createImageForPayload:(NSString *)payload CF_RETURNS_RETAINED;
+ (NSArray<NSString *> *)payloadsInCGImage:(CGImageRef)image;
+ (NSArray<NSString *> *)payloadsInCIImage:(CIImage *)image NS_SWIFT_NAME(payloads(in:));
+ (NSArray<NSString *> *)decodeImageData:(NSData *)data error:(NSError **)error NS_SWIFT_NAME(decode(data:));
+ (nullable NSData *)PNGForPayload:(NSString *)payload NS_SWIFT_NAME(png(payload:));
@end
NS_ASSUME_NONNULL_END
