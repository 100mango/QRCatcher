#import <CoreData/CoreData.h>
@class URLEntity;
NS_ASSUME_NONNULL_BEGIN
/// Owns the original QR model and Documents/coredata.sqlite store. Never discards an unreadable store.
@interface QRHistoryStore : NSObject
@property (nonatomic, readonly, nullable) NSManagedObjectContext *context;
@property (nonatomic, readonly, nullable) NSError *loadError;
+ (NSManagedObjectModel *)model;
+ (NSDictionary *)migrationOptions;
- (instancetype)initWithURL:(nullable NSURL *)URL;
- (BOOL)recordPayload:(NSString *)payload error:(NSError **)error;
- (BOOL)save:(NSError **)error;
@end
NS_ASSUME_NONNULL_END
