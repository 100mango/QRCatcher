#import "QRHistoryStore.h"
#import "URLEntity.h"
@implementation QRHistoryStore
+ (NSManagedObjectModel *)model {
    NSURL *URL = [[NSBundle bundleForClass:self] URLForResource:@"QR" withExtension:@"momd"];
    return [[NSManagedObjectModel alloc] initWithContentsOfURL:URL];
}
+ (NSDictionary *)migrationOptions {
    return @{NSMigratePersistentStoresAutomaticallyOption: @YES, NSInferMappingModelAutomaticallyOption: @YES};
}
- (instancetype)initWithURL:(NSURL *)URL {
    if ((self = [super init])) {
        NSPersistentStoreCoordinator *coordinator = [[NSPersistentStoreCoordinator alloc] initWithManagedObjectModel:[self.class model]];
        NSError *error;
        if (![coordinator addPersistentStoreWithType:URL ? NSSQLiteStoreType : NSInMemoryStoreType configuration:nil URL:URL options:[self.class migrationOptions] error:&error]) {
            _loadError = error;
            return self;
        }
        _context = [[NSManagedObjectContext alloc] initWithConcurrencyType:NSMainQueueConcurrencyType];
        _context.persistentStoreCoordinator = coordinator;
        _context.mergePolicy = NSMergeByPropertyObjectTrumpMergePolicy;
    }
    return self;
}
- (BOOL)recordPayload:(NSString *)payload error:(NSError **)error {
    NSAssert([NSThread isMainThread], @"History is used on the main queue");
    if (!self.context) { if (error) *error = self.loadError; return NO; }
    if (payload.length == 0) {
        if (error) *error = [NSError errorWithDomain:@"QRCatcher.History" code:1 userInfo:@{NSLocalizedDescriptionKey: @"The QR code is empty."}];
        return NO;
    }
    NSFetchRequest *request = [NSFetchRequest fetchRequestWithEntityName:@"URLEntity"];
    request.predicate = [NSPredicate predicateWithFormat:@"url == %@", payload];
    request.fetchLimit = 1;
    NSArray *existing = [self.context executeFetchRequest:request error:error];
    if (!existing) return NO;
    if (existing.count == 0) {
        URLEntity *record = [NSEntityDescription insertNewObjectForEntityForName:@"URLEntity" inManagedObjectContext:self.context];
        record.url = payload;
        record.createDate = [NSDate date];
    }
    return [self save:error];
}
- (BOOL)save:(NSError **)error {
    if (!self.context) { if (error) *error = self.loadError; return NO; }
    if (!self.context.hasChanges) return YES;
    return [self.context save:error];
}
@end
