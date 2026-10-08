#import <Foundation/Foundation.h>
NS_ASSUME_NONNULL_BEGIN
/// Serial cancellable imported-image pipeline for Objective-C platform adapters.
@interface QRImageImportQueue : NSObject
+ (NSOperation *)readWithLoader:(NSData * _Nullable (^)(NSError **error))loader completion:(void (^)(NSArray<NSString *> * _Nullable payloads, NSError * _Nullable error))completion;
@end
NS_ASSUME_NONNULL_END
