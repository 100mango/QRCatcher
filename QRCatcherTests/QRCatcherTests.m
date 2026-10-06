#import <XCTest/XCTest.h>
#import "QRHistoryStore.h"
#import "URLEntity.h"
#import "NSString+Tools.h"
#import "QRCodeCodec.h"
#import "QRImageCodec.h"
#import <CoreImage/CoreImage.h>
#import "AppDelegate.h"
#import "QRCatchViewController.h"
#import "QRURLViewController.h"
#import "QRPrivacyViewController.h"
#import <AVFoundation/AVFoundation.h>

@interface QRCatchViewController (RegressionTesting)
- (void)handlePayload:(NSString *)payload;
- (void)copyResult;
- (void)shareResult;
@end
@interface QRPrivacyViewController (RegressionTesting)
- (void)openExternalURL:(NSURL *)URL completion:(void (^)(BOOL))completion;
- (void)close;
@end
// Observe the app-owned external-opening boundary without opening a browser.
// The real UIButton action, pending guard and completion behavior still run.
@interface QRTestPrivacyController : QRPrivacyViewController
@property (nonatomic, strong) NSMutableArray<NSURL *> *openedURLs;
@property (nonatomic, copy) void (^pendingCompletion)(BOOL);
@end
@implementation QRTestPrivacyController
- (instancetype)init {
    if ((self = [super initWithNibName:nil bundle:nil])) _openedURLs = [NSMutableArray new];
    return self;
}
- (void)openExternalURL:(NSURL *)URL completion:(void (^)(BOOL))completion {
    [self.openedURLs addObject:URL];
    self.pendingCompletion = completion;
}
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
- (void)testSharedCodecMatchesOriginalUIImageOracle {
    for (NSString *name in @[@"ascii", @"unicode", @"rotated", @"invalid", @"multiple"]) {
        NSURL *URL = [[NSBundle bundleForClass:self.class] URLForResource:name withExtension:@"png"];
        XCTAssertNotNil(URL);
        NSData *data = [NSData dataWithContentsOfURL:URL];
        UIImage *image = [UIImage imageWithData:data];
        XCTAssertNotNil(image);
        // Frozen baseline algorithm from 9abdd5e; independent of the new adapter.
        CIImage *input = [[CIImage alloc] initWithImage:image];
        CIDetector *detector = [CIDetector detectorOfType:CIDetectorTypeQRCode context:nil options:@{CIDetectorAccuracy: CIDetectorAccuracyHigh}];
        NSMutableArray *oracle = [NSMutableArray new];
        for (CIQRCodeFeature *feature in [detector featuresInImage:input]) if (feature.messageString.length) [oracle addObject:feature.messageString];
        NSError *error;
        NSArray *portable = [QRImageCodec decodeImageData:data error:&error];
        XCTAssertNil(error);
        XCTAssertEqualObjects([NSSet setWithArray:portable], [NSSet setWithArray:oracle]);
        XCTAssertEqualObjects([QRCodeCodec payloadsInImage:image], oracle);
        XCTAssertEqual(oracle.count, [name isEqualToString:@"invalid"] ? 0 : [name isEqualToString:@"multiple"] ? 2 : 1);
    }
}
- (void)testPreviewRotationMappingAndSavedSelectionPreserveHistory {
    XCTAssertEqual([QRCatchViewController previewRotationForOrientation:UIInterfaceOrientationPortrait], 90);
    XCTAssertEqual([QRCatchViewController previewRotationForOrientation:UIInterfaceOrientationLandscapeLeft], 0);
    XCTAssertEqual([QRCatchViewController previewRotationForOrientation:UIInterfaceOrientationLandscapeRight], 180);
    XCTAssertEqual([QRCatchViewController previewRotationForOrientation:UIInterfaceOrientationPortraitUpsideDown], 270);
    QRHistoryStore *original = AppDelegate.appDelegate.historyStore;
    @try {
        QRHistoryStore *history = [[QRHistoryStore alloc] initWithURL:nil];
        AppDelegate.appDelegate.historyStore = history;
        NSError *error;
        XCTAssertTrue([history recordPayload:@"Selected old payload" error:&error]);
        NSFetchRequest *request = [NSFetchRequest fetchRequestWithEntityName:@"URLEntity"];
        NSArray<URLEntity *> *before = [history.context executeFetchRequest:request error:&error];
        NSDate *date = before.firstObject.createDate;
        QRCatchViewController *scanner = [QRCatchViewController new];
        [scanner showSavedPayload:@"Selected old payload"];
        UILabel *result = (UILabel *)[self viewWithIdentifier:@"scan.result" inView:scanner.view];
        XCTAssertEqualObjects(result.text, @"Selected old payload");
        [scanner showSavedPayload:@"Another saved selection"];
        XCTAssertEqualObjects(result.text, @"Another saved selection");
        XCTAssertEqual([history.context countForFetchRequest:request error:&error], 1);
        XCTAssertEqualObjects(before.firstObject.createDate, date);
        XCTAssertFalse([self viewWithIdentifier:@"scan.share" inView:scanner.view].hidden);
    } @finally { AppDelegate.appDelegate.historyStore = original; }
}
- (void)testSmallestHistoricalPhoneGeometryWithLargestText {
    for (NSValue *sizeValue in @[[NSValue valueWithCGSize:CGSizeMake(320,568)], [NSValue valueWithCGSize:CGSizeMake(568,320)]]) {
        CGSize size = sizeValue.CGSizeValue;
        UIViewController *host = [UIViewController new];
        host.view = [[UIView alloc] initWithFrame:(CGRect){CGPointZero, size}];
        QRCatchViewController *scanner = [QRCatchViewController new];
        [host addChildViewController:scanner];
        UITraitCollection *traits = [UITraitCollection traitCollectionWithTraitsFromCollections:@[
            [UITraitCollection traitCollectionWithHorizontalSizeClass:UIUserInterfaceSizeClassCompact],
            [UITraitCollection traitCollectionWithPreferredContentSizeCategory:UIContentSizeCategoryAccessibilityExtraExtraExtraLarge]
        ]];
        [host setOverrideTraitCollection:traits forChildViewController:scanner];
        [traits performAsCurrentTraitCollection:^{
            [scanner loadViewIfNeeded];
            scanner.view.frame = host.view.bounds;
            [host.view addSubview:scanner.view]; [scanner didMoveToParentViewController:host];
            [scanner showSavedPayload:@"Long QR text 你好 that must remain readable and keep copy, share, scan again and import reachable at the smallest historical phone geometry."];
        }];
        [host.view layoutIfNeeded]; [scanner.view layoutIfNeeded];
        UIScrollView *scroll = (UIScrollView *)scanner.view.subviews.firstObject;
        XCTAssertTrue([scroll isKindOfClass:UIScrollView.class]);
        [scroll layoutIfNeeded];
        UILabel *result = (UILabel *)[self viewWithIdentifier:@"scan.result" inView:scanner.view];
        XCTAssertGreaterThan(result.font.pointSize, 17);
        XCTAssertGreaterThan(scroll.contentSize.height, scroll.bounds.size.height);
        for (NSString *identifier in @[@"scan.copy", @"scan.share", @"scan.again", @"scan.import"]) {
            UIView *control = [self viewWithIdentifier:identifier inView:scanner.view];
            XCTAssertNotNil(control); XCTAssertFalse(control.hidden);
            CGRect rect = [control convertRect:control.bounds toView:scroll];
            XCTAssertGreaterThanOrEqual(CGRectGetMinX(rect), 0);
            XCTAssertLessThanOrEqual(CGRectGetMaxX(rect), scroll.bounds.size.width + 0.5);
            XCTAssertGreaterThanOrEqual(rect.size.height, 43.5);
            XCTAssertTrue([control isKindOfClass:NSClassFromString(@"QRActionButton")]);
            UIButton *button = (UIButton *)control;
            [button layoutIfNeeded];
            CGSize fullTitle = [button.titleLabel sizeThatFits:CGSizeMake(button.titleLabel.bounds.size.width, CGFLOAT_MAX)];
            NSLog(@"FULL_BUTTON_TITLE_GEOMETRY %@ button=%@ title=%@ measured=%@ font=%f line=%f", identifier, NSStringFromCGRect(button.bounds), NSStringFromCGRect(button.titleLabel.frame), NSStringFromCGSize(fullTitle), button.titleLabel.font.pointSize, button.titleLabel.font.lineHeight);
            XCTAssertGreaterThanOrEqual(button.titleLabel.bounds.size.height + 0.5, fullTitle.height, @"The entire title must fit vertically: %@", button.currentTitle);
            XCTAssertGreaterThanOrEqual(button.titleLabel.bounds.size.width + 0.5, fullTitle.width, @"The entire title must fit horizontally: %@", button.currentTitle);
            XCTAssertTrue(CGRectContainsRect(CGRectInset(button.bounds, -0.5, -0.5), [button.titleLabel convertRect:button.titleLabel.bounds toView:button]), @"Title escaped button bounds: %@", button.currentTitle);
            [scroll scrollRectToVisible:rect animated:NO]; [scroll layoutIfNeeded];
            XCTAssertGreaterThanOrEqual(CGRectGetHeight(CGRectIntersection(rect, scroll.bounds)), rect.size.height - 0.5);
        }
        UIGraphicsImageRenderer *renderer = [[UIGraphicsImageRenderer alloc] initWithSize:size];
        UIImage *image = [renderer imageWithActions:^(UIGraphicsImageRendererContext *context) { [scanner.view.layer renderInContext:context.CGContext]; }];
        XCTAttachment *attachment = [XCTAttachment attachmentWithData:UIImageJPEGRepresentation(image, 0.6) uniformTypeIdentifier:@"public.jpeg"];
        attachment.name = size.width == 320 ? @"view-layout-320x568-largest-text" : @"view-layout-568x320-largest-text";
        attachment.lifetime = XCTAttachmentLifetimeKeepAlways; [self addAttachment:attachment];
        [scanner willMoveToParentViewController:nil]; [scanner.view removeFromSuperview]; [scanner removeFromParentViewController];
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
- (void)testPrivacyOfflineBodyAndExplicitBrowserActionKeepCloseIdempotent {
    QRTestPrivacyController *privacy = [QRTestPrivacyController new];
    [privacy loadViewIfNeeded];
    UILabel *body = (UILabel *)[self viewWithIdentifier:@"privacy.body" inView:privacy.view];
    UILabel *notice = (UILabel *)[self viewWithIdentifier:@"privacy.websiteNotice" inView:privacy.view];
    UIView *error = [self viewWithIdentifier:@"privacy.error" inView:privacy.view];
    UIButton *open = (UIButton *)[self viewWithIdentifier:@"privacy.externalPolicy" inView:privacy.view];
    NSString *approved = @"Celluloid, QRCatcher, and TouchColor process photos, camera images, QR codes, or color data locally on your device. The developer does not collect or upload this data. Actions you choose to take, such as sharing or opening links, and system services such as iCloud sync are handled by the respective services. For privacy questions, contact 100mango@gmail.com. Local data can be deleted through the relevant app or system, and permissions can be revoked in system settings.";
    XCTAssertTrue([body isKindOfClass:UILabel.class]);
    XCTAssertEqualObjects(body.text, NSLocalizedString(approved, nil));
    XCTAssertEqual(body.numberOfLines, 0);
    XCTAssertTrue(body.adjustsFontForContentSizeCategory);
    XCTAssertTrue(notice.adjustsFontForContentSizeCategory);
    XCTAssertEqualObjects(notice.text, NSLocalizedString(@"GitHub Pages records visitor IP addresses for security.", nil));
    XCTAssertTrue([[self viewWithIdentifier:@"privacy.content" inView:privacy.view] isKindOfClass:UIScrollView.class]);
    XCTAssertNotNil(open);
    XCTAssertTrue(open.titleLabel.adjustsFontForContentSizeCategory);
    XCTAssertNil([self viewWithIdentifier:@"privacy.retry" inView:privacy.view]);
    XCTAssertEqual(privacy.openedURLs.count, 0, @"Loading the local policy must not request a website.");
    XCTAssertTrue(error.hidden);
    [open sendActionsForControlEvents:UIControlEventTouchUpInside];
    [open sendActionsForControlEvents:UIControlEventTouchUpInside];
    XCTAssertEqual(privacy.openedURLs.count, 1, @"An in-flight explicit action must not open twice.");
    XCTAssertEqualObjects(privacy.openedURLs.firstObject.absoluteString, @"https://100mango.github.io/app-privacy/");
    XCTAssertFalse(open.enabled);
    XCTAssertNotNil(privacy.pendingCompletion);
    privacy.pendingCompletion(NO);
    XCTAssertTrue(open.enabled);
    XCTAssertFalse(error.hidden);
    XCTAssertEqualObjects(body.text, NSLocalizedString(approved, nil));
    [open sendActionsForControlEvents:UIControlEventTouchUpInside];
    XCTAssertEqual(privacy.openedURLs.count, 2);
    privacy.pendingCompletion(YES);
    XCTAssertTrue(error.hidden);
    XCTAssertTrue(open.enabled);
    XCTAssertEqualObjects(body.text, NSLocalizedString(approved, nil));
    [open sendActionsForControlEvents:UIControlEventTouchUpInside];
    __block NSInteger cleanupCount = 0;
    privacy.dismissalHandler = ^{ cleanupCount += 1; };
    [privacy close]; [privacy close];
    XCTAssertEqual(cleanupCount, 1);
    privacy.pendingCompletion(NO);
    [open sendActionsForControlEvents:UIControlEventTouchUpInside];
    XCTAssertEqual(privacy.openedURLs.count, 3);
    XCTAssertTrue(error.hidden, @"A late browser completion cannot change a dismissed screen.");
    QRTestPrivacyController *reopened = [QRTestPrivacyController new];
    [reopened loadViewIfNeeded];
    XCTAssertEqual(reopened.openedURLs.count, 0);
    XCTAssertEqualObjects(((UILabel *)[self viewWithIdentifier:@"privacy.body" inView:reopened.view]).text, NSLocalizedString(approved, nil));
}
@end
