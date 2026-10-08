#import <Foundation/Foundation.h>
NS_ASSUME_NONNULL_BEGIN
/// Explicit Watch photo requests only; never mutates the phone's scan history.
@interface QRWatchPhoneService : NSObject
+ (instancetype)shared;
- (void)activate;
/// Bounded protocol/codec boundary, also tested without pretending transport delivery.
- (nullable NSData *)decodedResponseForRequestData:(NSData *)data;
- (BOOL)requestData:(NSData *)left matchesRequest:(NSData *)right;
@end
NS_ASSUME_NONNULL_END
