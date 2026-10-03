#import "QRCodeCodec.h"
#import <CoreImage/CoreImage.h>
@implementation QRCodeCodec
+ (UIImage *)imageForPayload:(NSString *)payload {
    if (payload.length == 0) return nil;
    CIFilter *filter = [CIFilter filterWithName:@"CIQRCodeGenerator"];
    [filter setValue:[payload dataUsingEncoding:NSUTF8StringEncoding] forKey:@"inputMessage"];
    [filter setValue:@"M" forKey:@"inputCorrectionLevel"];
    CIImage *output = filter.outputImage;
    if (!output) return nil;
    CIImage *scaled = [output imageByApplyingTransform:CGAffineTransformMakeScale(8, 8)];
    CGImageRef cgImage = [[CIContext contextWithOptions:nil] createCGImage:scaled fromRect:scaled.extent];
    UIImage *image = [UIImage imageWithCGImage:cgImage];
    CGImageRelease(cgImage);
    return image;
}
+ (NSArray<NSString *> *)payloadsInImage:(UIImage *)image {
    CIImage *input = image.CIImage ?: [[CIImage alloc] initWithImage:image];
    if (!input) return @[];
    CIDetector *detector = [CIDetector detectorOfType:CIDetectorTypeQRCode context:nil options:@{CIDetectorAccuracy: CIDetectorAccuracyHigh}];
    NSMutableArray *results = [NSMutableArray new];
    for (CIQRCodeFeature *feature in [detector featuresInImage:input]) {
        if (feature.messageString.length) [results addObject:feature.messageString];
    }
    return results;
}
@end
