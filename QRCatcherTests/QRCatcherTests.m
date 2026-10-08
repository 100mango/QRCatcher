#import <XCTest/XCTest.h>
#import "QRHistoryStore.h"
#import "URLEntity.h"
#import "NSString+Tools.h"
#import "QRCodeCodec.h"
#import "AppDelegate.h"
#import "QRCatchViewController.h"
#import "QRURLViewController.h"
#import "QRPrivacyViewController.h"
#import <WebKit/WebKit.h>
#import <AVFoundation/AVFoundation.h>

@interface QRCatchViewController (RegressionTesting)
- (void)handlePayload:(NSString *)payload;
- (void)copyResult;
@end
@interface QRPrivacyViewController (RegressionTesting) <WKNavigationDelegate>
- (void)loadPolicy;
- (void)close;
@end
// WKNavigationResponse has no public initializer. Supply transport facts to the
// actual navigation delegate, without substituting its error-handling behavior.
@interface QRTestNavigationResponse : NSObject
@property (nonatomic, strong) NSURLResponse *response;
@property (nonatomic, getter=isForMainFrame) BOOL forMainFrame;
@property (nonatomic) BOOL canShowMIMEType;
@end
@implementation QRTestNavigationResponse
@end
@interface QRCatcherTests : XCTestCase
@end
@implementation QRCatcherTests
+ (void)setUp {
    [super setUp];
    NSLog(@"Camera capability observation: authorization=%ld device=%@ (hosted tests do not simulate permission grants)",
          (long)[AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeVideo],
          [AVCaptureDevice defaultDeviceWithMediaType:AVMediaTypeVideo] ? @"present" : @"absent");
}
- (UIView *)viewWithIdentifier:(NSString *)identifier inView:(UIView *)view {
    if ([view.accessibilityIdentifier isEqualToString:identifier]) return view;
    for (UIView *child in view.subviews) {
        UIView *match = [self viewWithIdentifier:identifier inView:child];
        if (match) return match;
    }
    return nil;
}
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
- (void)testNonQRCodeImageDoesNotDecode {
    UIGraphicsImageRenderer *renderer = [[UIGraphicsImageRenderer alloc] initWithSize:CGSizeMake(128, 128)];
    UIImage *plain = [renderer imageWithActions:^(UIGraphicsImageRendererContext *context) {
        [UIColor.whiteColor setFill];
        [context fillRect:CGRectMake(0, 0, 128, 128)];
    }];
    XCTAssertEqual([QRCodeCodec payloadsInImage:plain].count, 0);
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
- (void)testCorruptHistoryShowsErrorAndStillAllowsCopy {
    NSURL *URL = [NSURL fileURLWithPath:[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString]];
    NSData *sentinel = [@"preserve corrupt history bytes" dataUsingEncoding:NSUTF8StringEncoding];
    XCTAssertTrue([sentinel writeToURL:URL atomically:YES]);
    QRHistoryStore *original = AppDelegate.appDelegate.historyStore;
    NSArray *originalPasteboard = UIPasteboard.generalPasteboard.items;
    @try {
        AppDelegate.appDelegate.historyStore = [[QRHistoryStore alloc] initWithURL:URL];
        QRURLViewController *history = [QRURLViewController new];
        [history loadViewIfNeeded];
        UILabel *error = (UILabel *)[self viewWithIdentifier:@"history.empty" inView:history.view];
        XCTAssertEqualObjects(error.text, NSLocalizedString(@"History could not be loaded. Your saved data has not been erased. Please restart the app and try again.", nil));
        XCTAssertEqual([(UITableView *)history.view numberOfRowsInSection:0], 0);
        QRCatchViewController *scanner = [QRCatchViewController new];
        [scanner loadViewIfNeeded];
        [scanner handlePayload:@"Copy survives a storage failure 你好"];
        UILabel *status = (UILabel *)[self viewWithIdentifier:@"scan.status" inView:scanner.view];
        XCTAssertEqualObjects(status.text, NSLocalizedString(@"QR code read, but history could not be saved. Your existing history has not been erased.", nil));
        [scanner copyResult];
        XCTAssertEqualObjects(UIPasteboard.generalPasteboard.string, @"Copy survives a storage failure 你好");
        XCTAssertEqualObjects([NSData dataWithContentsOfURL:URL], sentinel);
    } @finally {
        AppDelegate.appDelegate.historyStore = original;
        UIPasteboard.generalPasteboard.items = originalPasteboard;
        [NSFileManager.defaultManager removeItemAtURL:URL error:nil];
    }
}
- (void)testPrivacyHTTPFailuresAndWebProcessTerminationOfferRetry {
    QRPrivacyViewController *privacy = [QRPrivacyViewController new];
    [privacy loadViewIfNeeded];
    WKWebView *web = (WKWebView *)[self viewWithIdentifier:@"privacy.content" inView:privacy.view];
    [web stopLoading];
    UIView *error = [self viewWithIdentifier:@"privacy.error" inView:privacy.view].superview;
    UIButton *retry = (UIButton *)[self viewWithIdentifier:@"privacy.retry" inView:privacy.view];
    XCTAssertFalse(web.configuration.websiteDataStore.persistent);
    XCTAssertFalse(web.configuration.defaultWebpagePreferences.allowsContentJavaScript);
    for (NSNumber *code in @[@200, @404, @500]) {
        [privacy loadPolicy]; [web stopLoading];
        QRTestNavigationResponse *response = [QRTestNavigationResponse new];
        response.response = [[NSHTTPURLResponse alloc] initWithURL:[NSURL URLWithString:@"https://100mango.github.io/app-privacy/"] statusCode:code.integerValue HTTPVersion:@"HTTP/1.1" headerFields:@{@"Content-Type": @"text/html"}];
        response.forMainFrame = YES; response.canShowMIMEType = YES;
        __block WKNavigationResponsePolicy decision = WKNavigationResponsePolicyCancel;
        [privacy webView:web decidePolicyForNavigationResponse:(WKNavigationResponse *)response decisionHandler:^(WKNavigationResponsePolicy value) { decision = value; }];
        XCTAssertEqual(decision, code.integerValue == 200 ? WKNavigationResponsePolicyAllow : WKNavigationResponsePolicyCancel);
        XCTAssertEqual(error.hidden, code.integerValue == 200);
        if (code.integerValue != 200) {
            XCTAssertTrue(web.hidden);
            XCTAssertEqualObjects(retry.currentTitle, NSLocalizedString(@"Retry", nil));
            [retry sendActionsForControlEvents:UIControlEventTouchUpInside];
            XCTAssertTrue(error.hidden); XCTAssertFalse(web.hidden);
            [web stopLoading];
        }
    }
    [privacy webViewWebContentProcessDidTerminate:web];
    XCTAssertFalse(error.hidden); XCTAssertTrue(web.hidden);
    [retry sendActionsForControlEvents:UIControlEventTouchUpInside];
    XCTAssertTrue(error.hidden); XCTAssertFalse(web.hidden); [web stopLoading];
    __block NSInteger cleanupCount = 0;
    privacy.dismissalHandler = ^{ cleanupCount += 1; };
    [privacy close]; [privacy close];
    XCTAssertEqual(cleanupCount, 1);
    [privacy webViewWebContentProcessDidTerminate:web];
    XCTAssertTrue(error.hidden, @"Late WebKit callbacks must not replace a dismissed screen with an error.");
}
@end
