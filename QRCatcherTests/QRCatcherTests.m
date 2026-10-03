#import <XCTest/XCTest.h>
#import "QRHistoryStore.h"
#import "URLEntity.h"
#import "NSString+Tools.h"
#import "QRCodeCodec.h"
@interface QRCatcherTests : XCTestCase
@end
@implementation QRCatcherTests
- (void)testQRRoundTrip {
    for (NSString *payload in @[@"https://example.com/path?q=one", @"QRCatcher 你好 123"]) {
        UIImage *image = [QRCodeCodec imageForPayload:payload];
        XCTAssertNotNil(image);
        XCTAssertEqualObjects([QRCodeCodec payloadsInImage:image].firstObject, payload);
    }
}
- (void)testEmptyQR {
    XCTAssertNil([QRCodeCodec imageForPayload:@""]);
    XCTAssertEqual([QRCodeCodec payloadsInImage:[UIImage new]].count, 0);
}
- (void)testSafeWebsiteClassification {
    XCTAssertEqualObjects([NSString HTTPURLFromString:@"example.com"].absoluteString, @"https://example.com");
    XCTAssertNotNil([NSString HTTPURLFromString:@"HTTPS://example.com/a?q=1"]);
    for (NSString *value in @[@"", @"plain text", @"javascript:alert(1)", @"file:///etc/passwd", @"tel:123", @"https://user:secret@example.com", @"http://"]) XCTAssertNil([NSString HTTPURLFromString:value]);
}
- (void)testHistoryDeduplicatesAndDeletes {
    QRHistoryStore *store = [[QRHistoryStore alloc] initWithURL:nil];
    XCTAssertNil(store.loadError);
    NSError *error;
    XCTAssertTrue([store recordPayload:@"hello" error:&error]);
    XCTAssertTrue([store recordPayload:@"hello" error:&error]);
    NSFetchRequest *request = [NSFetchRequest fetchRequestWithEntityName:@"URLEntity"];
    NSArray *records = [store.context executeFetchRequest:request error:&error];
    XCTAssertEqual(records.count, 1);
    XCTAssertNotNil(((URLEntity *)records.firstObject).createDate);
    [store.context deleteObject:records.firstObject];
    XCTAssertTrue([store save:&error]);
    XCTAssertEqual([store.context countForFetchRequest:request error:&error], 0);
    XCTAssertFalse([store recordPayload:@"" error:&error]);
}
- (void)testLegacyStoreReopensWithoutLosingHistory {
    NSURL *directory = [NSURL fileURLWithPath:[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString]];
    [NSFileManager.defaultManager createDirectoryAtURL:directory withIntermediateDirectories:YES attributes:nil error:nil];
    NSURL *URL = [directory URLByAppendingPathComponent:@"coredata.sqlite"];
    NSError *error;
    // Build the store with the original unchanged model, using the original SQLite options.
    NSPersistentStoreCoordinator *legacy = [[NSPersistentStoreCoordinator alloc] initWithManagedObjectModel:[QRHistoryStore model]];
    NSPersistentStore *persistent = [legacy addPersistentStoreWithType:NSSQLiteStoreType configuration:nil URL:URL options:nil error:&error];
    XCTAssertNotNil(persistent);
    NSManagedObjectContext *context = [[NSManagedObjectContext alloc] initWithConcurrencyType:NSMainQueueConcurrencyType];
    context.persistentStoreCoordinator = legacy;
    URLEntity *record = [NSEntityDescription insertNewObjectForEntityForName:@"URLEntity" inManagedObjectContext:context];
    record.url = @"http://example.com/legacy"; record.createDate = [NSDate dateWithTimeIntervalSince1970:1431993600];
    XCTAssertTrue([context save:&error]);
    [context reset];
    XCTAssertTrue([legacy removePersistentStore:persistent error:&error]);
    QRHistoryStore *modern = [[QRHistoryStore alloc] initWithURL:URL];
    XCTAssertNil(modern.loadError);
    NSFetchRequest *request = [NSFetchRequest fetchRequestWithEntityName:@"URLEntity"];
    NSArray *records = [modern.context executeFetchRequest:request error:&error];
    XCTAssertEqual(records.count, 1);
    XCTAssertEqualObjects(((URLEntity *)records.firstObject).url, @"http://example.com/legacy");
    XCTAssertEqualObjects(((URLEntity *)records.firstObject).createDate, [NSDate dateWithTimeIntervalSince1970:1431993600]);
    XCTAssertTrue([modern recordPayload:@"new text" error:&error]);
    XCTAssertEqual([modern.context countForFetchRequest:request error:&error], 2);
    NSPersistentStore *store = modern.context.persistentStoreCoordinator.persistentStores.firstObject;
    [modern.context reset];
    XCTAssertTrue([modern.context.persistentStoreCoordinator removePersistentStore:store error:&error]);
    QRHistoryStore *reopened = [[QRHistoryStore alloc] initWithURL:URL];
    XCTAssertEqual([reopened.context countForFetchRequest:request error:&error], 2);
    [reopened.context reset];
    [reopened.context.persistentStoreCoordinator removePersistentStore:reopened.context.persistentStoreCoordinator.persistentStores.firstObject error:nil];
    [NSFileManager.defaultManager removeItemAtURL:directory error:nil];
}
- (void)testUnreadableStoreIsNotDeleted {
    NSURL *URL = [NSURL fileURLWithPath:[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString]];
    NSData *sentinel = [@"not a sqlite database" dataUsingEncoding:NSUTF8StringEncoding];
    [sentinel writeToURL:URL atomically:YES];
    QRHistoryStore *store = [[QRHistoryStore alloc] initWithURL:URL];
    XCTAssertNotNil(store.loadError); XCTAssertNil(store.context);
    XCTAssertEqualObjects([NSData dataWithContentsOfURL:URL], sentinel);
    NSError *error;
    XCTAssertFalse([store recordPayload:@"test" error:&error]);
    [NSFileManager.defaultManager removeItemAtURL:URL error:nil];
}
@end
