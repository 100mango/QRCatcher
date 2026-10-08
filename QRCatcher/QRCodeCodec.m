#import "QRCodeCodec.h"
#import "QRImageCodec.h"
#import <CoreImage/CoreImage.h>
@implementation QRCodeCodec
+ (UIImage *)imageForPayload:(NSString *)payload {
    CGImageRef cgImage = [QRImageCodec createImageForPayload:payload];
    if (!cgImage) return nil;
    UIImage *image = [UIImage imageWithCGImage:cgImage];
    CGImageRelease(cgImage);
    return image;
}
+ (NSArray<NSString *> *)payloadsInImage:(UIImage *)image {
    if (!image.CGImage && !image.CIImage) return @[];
    CIImage *input = image.CIImage ?: [[CIImage alloc] initWithImage:image];
    return input ? [QRImageCodec payloadsInCIImage:input] : @[];
}
@end
