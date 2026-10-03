#import <XCTest/XCTest.h>
#import "QRBoundedImageFileReader.h"
#import "QRImageCodec.h"
#import "QRCatchViewController.h"
#import "AppDelegate.h"
#import "URLEntity.h"

@interface QRCatchViewController (BoundedImportTesting)
- (void)readPhotoProvider:(NSItemProvider *)provider generation:(NSUInteger)generation;
- (void)scanAgain;
@end
/// A public NSItemProvider adapter double controls callback lifetime, not decode.
@interface QRScopedImageProvider : NSItemProvider
@property (nonatomic, copy) void (^fileCompletion)(NSURL *, NSError *);
@property (nonatomic, strong) NSProgress *progress;
@property (nonatomic) NSUInteger dataLoads;
@end
@implementation QRScopedImageProvider
- (NSArray<NSString *> *)registeredTypeIdentifiers { return @[@"public.png"]; }
- (NSProgress *)loadFileRepresentationForTypeIdentifier:(NSString *)identifier completionHandler:(void (^)(NSURL *, NSError *))completionHandler {
    self.fileCompletion = completionHandler; self.progress = [NSProgress progressWithTotalUnitCount:1]; return self.progress;
}
- (NSProgress *)loadDataRepresentationForTypeIdentifier:(NSString *)identifier completionHandler:(void (^)(NSData *, NSError *))completionHandler {
    self.dataLoads += 1; return [NSProgress progressWithTotalUnitCount:1];
}
@end

@interface QRBoundedImageImportTests : XCTestCase
@property (nonatomic, strong) NSURL *folder;
@property (nonatomic, strong) QRHistoryStore *original;
@property (nonatomic, strong) QRCatchViewController *scanner;
@end
@implementation QRBoundedImageImportTests
- (void)setUp {
    [super setUp];
    self.folder = [NSURL fileURLWithPath:[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString] isDirectory:YES];
    XCTAssertTrue([NSFileManager.defaultManager createDirectoryAtURL:self.folder withIntermediateDirectories:YES attributes:nil error:nil]);
    self.original = AppDelegate.appDelegate.historyStore;
    AppDelegate.appDelegate.historyStore = [[QRHistoryStore alloc] initWithURL:[self.folder URLByAppendingPathComponent:@"history.sqlite"]];
}
- (void)tearDown {
    if (self.scanner) {
        [self.scanner scanAgain];
        NSOperation *operation = [self.scanner valueForKey:@"importOperation"];
        [operation waitUntilFinished]; self.scanner = nil;
    }
    NSManagedObjectContext *context = AppDelegate.appDelegate.historyStore.context;
    [context reset];
    for (NSPersistentStore *store in context.persistentStoreCoordinator.persistentStores.copy) {
        XCTAssertTrue([context.persistentStoreCoordinator removePersistentStore:store error:nil]);
    }
    AppDelegate.appDelegate.historyStore = self.original;
    [NSFileManager.defaultManager removeItemAtURL:self.folder error:nil];
    [super tearDown];
}
- (NSURL *)file:(NSString *)name data:(NSData *)data {
    NSURL *URL = [self.folder URLByAppendingPathComponent:name]; XCTAssertTrue([data writeToURL:URL atomically:YES]); return URL;
}
- (NSData *)fixture {
    NSURL *URL = [[NSBundle bundleForClass:self.class] URLForResource:@"unicode" withExtension:@"png"];
    XCTAssertNotNil(URL); return [NSData dataWithContentsOfURL:URL];
}
- (NSUInteger)historyCount {
    return [AppDelegate.appDelegate.historyStore.context countForFetchRequest:[NSFetchRequest fetchRequestWithEntityName:@"URLEntity"] error:nil];
}
- (void)prepareScanner {
    XCTAssertTrue([AppDelegate.appDelegate.historyStore recordPayload:@"Keep previous result" error:nil]);
    self.scanner = [QRCatchViewController new]; [self.scanner loadViewIfNeeded];
    [self.scanner showSavedPayload:@"Keep previous result"];
    [self.scanner setValue:@7 forKey:@"importGeneration"]; [self.scanner setValue:@YES forKey:@"importing"];
}
- (void)waitForStatusContaining:(NSString *)text {
    UILabel *status = [self.scanner valueForKey:@"statusLabel"];
    [self expectationForPredicate:[NSPredicate predicateWithFormat:@"text CONTAINS %@", text] evaluatedWithObject:status handler:nil];
    [self waitForExpectationsWithTimeout:5 handler:nil];
}
- (void)testSnapshotOwnsExactBytesAfterOriginalFileDisappears {
    NSData *source = self.fixture; NSURL *URL = [self file:@"provider.png" data:source]; NSError *error;
    NSData *snapshot = [QRBoundedImageFileReader readURL:URL isCancelled:^BOOL { return NO; } error:&error];
    XCTAssertNil(error); XCTAssertEqualObjects(snapshot, source);
    XCTAssertTrue([NSFileManager.defaultManager removeItemAtURL:URL error:nil]);
    XCTAssertEqualObjects([QRImageCodec decodeImageData:snapshot error:&error], (@[@"QRCatcher 你好 🌈 123"]));
}
- (void)testOversizedSparseFileSymlinkDirectoryAndMissingFileReject {
    NSURL *URL = [self file:@"large.png" data:[NSData data]];
    NSFileHandle *handle = [NSFileHandle fileHandleForWritingToURL:URL error:nil];
    [handle truncateFileAtOffset:QRMaximumImportedImageBytes + 1]; [handle closeFile];
    NSError *error;
    XCTAssertNil([QRBoundedImageFileReader readURL:URL isCancelled:^BOOL { return NO; } error:&error]); XCTAssertNotNil(error);
    NSURL *link = [self.folder URLByAppendingPathComponent:@"link.png"];
    XCTAssertTrue([NSFileManager.defaultManager createSymbolicLinkAtURL:link withDestinationURL:URL error:nil]);
    for (NSURL *candidate in @[link,self.folder,[self.folder URLByAppendingPathComponent:@"missing.png"]]) {
        error = nil; XCTAssertNil([QRBoundedImageFileReader readURL:candidate isCancelled:^BOOL { return NO; } error:&error]); XCTAssertNotNil(error);
    }
}
- (void)testGrowingSourceHitsActualByteCapAndTruncatedSourceRejects {
    for (NSNumber *newSize in @[@(QRMaximumImportedImageBytes + 1), @10]) {
        NSURL *URL = [self file:@"changing.png" data:[NSMutableData dataWithLength:256 * 1024]];
        __block NSUInteger checks = 0; NSError *error;
        NSData *value = [QRBoundedImageFileReader readURL:URL isCancelled:^BOOL {
            if (++checks == 3) {
                NSFileHandle *handle = [NSFileHandle fileHandleForWritingToURL:URL error:nil];
                [handle truncateFileAtOffset:newSize.unsignedLongLongValue]; [handle closeFile];
            }
            return NO;
        } error:&error];
        XCTAssertNil(value); XCTAssertNotNil(error);
        XCTAssertEqualObjects(error.domain, newSize.unsignedLongLongValue > QRMaximumImportedImageBytes ? @"QRCatcher.Image" : NSCocoaErrorDomain);
    }
}
- (void)testCancellationStopsBetweenChunks {
    NSURL *URL = [self file:@"cancel.png" data:[NSMutableData dataWithLength:256 * 1024]];
    __block NSUInteger checks = 0; NSError *error;
    XCTAssertNil([QRBoundedImageFileReader readURL:URL isCancelled:^BOOL { return ++checks == 3; } error:&error]);
    XCTAssertEqual(checks, 3); XCTAssertEqualObjects(error.domain, NSCocoaErrorDomain); XCTAssertEqual(error.code, NSUserCancelledError);
}
- (void)testPhotoProviderTemporaryLifetimeUsesRealDecoderAndPersistence {
    [self prepareScanner]; QRScopedImageProvider *provider = [QRScopedImageProvider new];
    [self.scanner readPhotoProvider:provider generation:7]; XCTAssertNotNil(provider.fileCompletion); XCTAssertEqual(provider.dataLoads, 0);
    NSURL *URL = [self file:@"ephemeral.png" data:self.fixture];
    provider.fileCompletion(URL,nil); // The real reader must finish before returning.
    XCTAssertTrue([NSFileManager.defaultManager removeItemAtURL:URL error:nil]);
    UILabel *result = [self.scanner valueForKey:@"resultLabel"];
    [self expectationForPredicate:[NSPredicate predicateWithFormat:@"text == %@", @"QRCatcher 你好 🌈 123"] evaluatedWithObject:result handler:nil];
    [self waitForExpectationsWithTimeout:5 handler:nil];
    XCTAssertEqual(self.historyCount, 2);
}
- (void)testTruncatedImageAndProviderErrorRetainPreviousResult {
    [self prepareScanner];
    for (NSNumber *providerFails in @[@NO,@YES]) {
        QRScopedImageProvider *provider = [QRScopedImageProvider new];
        [self.scanner setValue:@"Pending" forKeyPath:@"statusLabel.text"];
        [self.scanner readPhotoProvider:provider generation:7];
        NSData *prefix = [self.fixture subdataWithRange:NSMakeRange(0,20)];
        NSURL *URL = [self file:@"truncated.png" data:prefix];
        provider.fileCompletion(providerFails.boolValue ? nil : URL,providerFails.boolValue ? [NSError errorWithDomain:NSCocoaErrorDomain code:NSFileReadUnknownError userInfo:nil] : nil);
        [self waitForStatusContaining:@"could not be read"];
        XCTAssertEqualObjects([[self.scanner valueForKey:@"resultLabel"] text], @"Keep previous result"); XCTAssertEqual(self.historyCount,1);
    }
}
- (void)testCancelledAndStaleProviderCallbacksCannotReplaceNewSelection {
    [self prepareScanner]; NSURL *URL = [self file:@"late.png" data:self.fixture];
    QRScopedImageProvider *cancelled = [QRScopedImageProvider new]; [self.scanner readPhotoProvider:cancelled generation:7];
    [self.scanner showSavedPayload:@"Newest saved selection"];
    XCTAssertTrue(cancelled.progress.cancelled);
    cancelled.fileCompletion(URL,nil); // A misbehaving provider may still call back.
    NSUInteger generation = [[self.scanner valueForKey:@"importGeneration"] unsignedIntegerValue];
    QRScopedImageProvider *stale = [QRScopedImageProvider new]; [self.scanner readPhotoProvider:stale generation:generation];
    [self.scanner setValue:@(generation + 1) forKey:@"importGeneration"];
    stale.fileCompletion(URL,nil);
    XCTestExpectation *drained = [self expectationWithDescription:@"Queued generation check completed"];
    dispatch_async(dispatch_get_main_queue(), ^{ [drained fulfill]; }); [self waitForExpectationsWithTimeout:5 handler:nil];
    XCTAssertEqualObjects([[self.scanner valueForKey:@"resultLabel"] text], @"Newest saved selection"); XCTAssertEqual(self.historyCount,1);
}
@end
