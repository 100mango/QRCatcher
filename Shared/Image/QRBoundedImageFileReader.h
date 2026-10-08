#import <Foundation/Foundation.h>
NS_ASSUME_NONNULL_BEGIN
FOUNDATION_EXPORT NSUInteger const QRMaximumImportedImageBytes;
/// Owns a bounded snapshot synchronously, before a provider's temporary URL dies.
@interface QRBoundedImageFileReader : NSObject
+ (nullable NSData *)readURL:(NSURL *)URL isCancelled:(BOOL (^)(void))isCancelled error:(NSError **)error NS_SWIFT_NAME(read(_:isCancelled:));
@end
NS_ASSUME_NONNULL_END
