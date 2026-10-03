#import "QRImageCodec.h"
#import <CoreImage/CoreImage.h>
#import <ImageIO/ImageIO.h>
@implementation QRImageCodec
+ (CGImageRef)createImageForPayload:(NSString *)payload {
    if (payload.length == 0) return nil;
    CIFilter *filter = [CIFilter filterWithName:@"CIQRCodeGenerator"];
    [filter setValue:[payload dataUsingEncoding:NSUTF8StringEncoding] forKey:@"inputMessage"];
    [filter setValue:@"M" forKey:@"inputCorrectionLevel"];
    CIImage *output = filter.outputImage;
    if (!output) return nil;
    CIImage *scaled = [output imageByApplyingTransform:CGAffineTransformMakeScale(8, 8)];
    return [[CIContext contextWithOptions:nil] createCGImage:scaled fromRect:scaled.extent];
}
+ (NSArray<NSString *> *)payloadsInCGImage:(CGImageRef)image {
    return image ? [self payloadsInCIImage:[CIImage imageWithCGImage:image]] : @[];
}
+ (NSArray<NSString *> *)payloadsInCIImage:(CIImage *)image {
    CIDetector *detector = [CIDetector detectorOfType:CIDetectorTypeQRCode context:nil options:@{CIDetectorAccuracy: CIDetectorAccuracyHigh}];
    NSMutableArray *results = [NSMutableArray new];
    for (CIQRCodeFeature *feature in [detector featuresInImage:image]) {
        if (feature.messageString.length) [results addObject:feature.messageString];
    }
    return results;
}
+ (NSArray<NSString *> *)decodeImageData:(NSData *)data error:(NSError **)error {
    if (data.length == 0 || data.length > 50 * 1024 * 1024) {
        if (error) *error = [NSError errorWithDomain:@"QRCatcher.Image" code:1 userInfo:@{NSLocalizedDescriptionKey:NSLocalizedString(@"Choose an image smaller than 50 MB.", nil)}];
        return nil;
    }
    CGImageSourceRef source = CGImageSourceCreateWithData((__bridge CFDataRef)data, NULL);
    CGImageRef image = source ? CGImageSourceCreateThumbnailAtIndex(source, 0, (__bridge CFDictionaryRef)@{(id)kCGImageSourceCreateThumbnailFromImageAlways:@YES, (id)kCGImageSourceCreateThumbnailWithTransform:@YES, (id)kCGImageSourceThumbnailMaxPixelSize:@4096, (id)kCGImageSourceShouldCacheImmediately:@YES}) : nil;
    if (source) CFRelease(source);
    if (!image) {
        if (error) *error = [NSError errorWithDomain:@"QRCatcher.Image" code:2 userInfo:@{NSLocalizedDescriptionKey:NSLocalizedString(@"This file could not be read as an image.", nil)}];
        return nil;
    }
    NSArray *results = [self payloadsInCGImage:image];
    CGImageRelease(image);
    return results;
}
+ (NSData *)PNGForPayload:(NSString *)payload {
    CGImageRef code = [self createImageForPayload:payload];
    if (!code) return nil;
    // Four modules (32 px at 8 px/module) of quiet zone on every exported edge.
    size_t w = CGImageGetWidth(code) + 64, h = CGImageGetHeight(code) + 64;
    CGColorSpaceRef color = CGColorSpaceCreateDeviceRGB();
    CGContextRef context = CGBitmapContextCreate(NULL, w, h, 8, 0, color, (CGBitmapInfo)kCGImageAlphaPremultipliedLast);
    CGColorSpaceRelease(color);
    if (!context) { CGImageRelease(code); return nil; }
    CGContextSetRGBFillColor(context, 1, 1, 1, 1); CGContextFillRect(context, CGRectMake(0,0,w,h));
    CGContextSetInterpolationQuality(context, kCGInterpolationNone); CGContextDrawImage(context, CGRectMake(32,32,w-64,h-64), code);
    CGImageRef image = CGBitmapContextCreateImage(context); CGContextRelease(context); CGImageRelease(code);
    NSMutableData *data = [NSMutableData new];
    CGImageDestinationRef destination = CGImageDestinationCreateWithData((__bridge CFMutableDataRef)data, CFSTR("public.png"), 1, NULL);
    if (!destination || !image) { if(destination) CFRelease(destination); if(image) CGImageRelease(image); return nil; }
    CGImageDestinationAddImage(destination, image, NULL);
    BOOL success = CGImageDestinationFinalize(destination);
    CFRelease(destination); CGImageRelease(image);
    return success ? data : nil;
}
@end
