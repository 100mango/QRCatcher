#import <Foundation/Foundation.h>
NS_ASSUME_NONNULL_BEGIN
/// Foundation-only action policy, shared by every platform. Never opens a URL.
@interface QRPayload : NSObject
+ (nullable NSURL *)safeWebURL:(NSString *)payload NS_SWIFT_NAME(safeWebURL(_:));
@end
/// Value projection only: contains no storage objects, UI types or mutable state.
@interface QRHistoryValue : NSObject
@property (nonatomic, copy, readonly) NSString *identifier;
@property (nonatomic, copy, readonly, nullable) NSString *payload;
@property (nonatomic, copy, readonly, nullable) NSDate *createdAt;
- (instancetype)initWithIdentifier:(NSString *)identifier payload:(nullable NSString *)payload createdAt:(nullable NSDate *)createdAt;
- (NSDictionary<NSString *, id> *)exportValue;
@end
NS_ASSUME_NONNULL_END
