#import "QRImageImportQueue.h"
#import "QRImageCodec.h"
@implementation QRImageImportQueue
+ (NSOperationQueue *)queue {
    static NSOperationQueue *queue; static dispatch_once_t once;
    dispatch_once(&once, ^{ queue = [NSOperationQueue new]; queue.name = @"QRCatcher.imageImport"; queue.maxConcurrentOperationCount = 1; queue.qualityOfService = NSQualityOfServiceUserInitiated; });
    return queue;
}
+ (NSOperation *)readWithLoader:(NSData *(^)(NSError **))loader completion:(void (^)(NSArray<NSString *> *, NSError *))completion {
    NSBlockOperation *operation = [NSBlockOperation new];
    __weak NSBlockOperation *weakOperation = operation;
    [operation addExecutionBlock:^{
        @autoreleasepool {
            NSBlockOperation *current = weakOperation;
            if (!current || current.cancelled) return;
            NSError *error;
            NSData *data = loader(&error);
            if (current.cancelled) return;
            NSArray *values = data ? [QRImageCodec decodeImageData:data error:&error] : nil;
            if (current.cancelled) return;
            dispatch_async(dispatch_get_main_queue(), ^{ if (!current.cancelled) completion(values, error); });
        }
    }];
    [self.queue addOperation:operation];
    return operation;
}
@end
