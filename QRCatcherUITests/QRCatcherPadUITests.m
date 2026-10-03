#import <XCTest/XCTest.h>
#import <UIKit/UIKit.h>
@interface QRCatcherPadUITests : XCTestCase
@property (nonatomic, strong) XCUIApplication *app;
@end
@implementation QRCatcherPadUITests
- (void)setUp { [super setUp]; self.continueAfterFailure = NO; self.app = [XCUIApplication new]; }
- (void)tearDown { if (self.testRun.failureCount > 0) { NSLog(@"IPAD_FAILURE_UI:%@", self.app.debugDescription); [self capture:@"ipad-failure"]; } [self.app terminate]; XCUIDevice.sharedDevice.orientation = UIDeviceOrientationPortrait; [super tearDown]; }
- (void)launchWithArguments:(NSArray *)extra {
    self.app.launchArguments = [@[@"-ui-testing", @"-reset-history", @"-AppleLanguages", @"(en)", @"-AppleLocale", @"en_US", @"-fixture-payload", @"Native iPad QR result 你好"] arrayByAddingObjectsFromArray:extra];
    [self.app launch];
    XCTAssertTrue([self.app.staticTexts[@"scan.result"] waitForExistenceWithTimeout:15]);
}
- (void)capture:(NSString *)name {
    NSData *data = UIImageJPEGRepresentation(XCUIScreen.mainScreen.screenshot.image, 0.5);
    XCTAssertLessThanOrEqual(data.length, 800 * 1024);
    XCTAttachment *attachment = [XCTAttachment attachmentWithData:data uniformTypeIdentifier:@"public.jpeg"];
    attachment.name = name; attachment.lifetime = XCTAttachmentLifetimeKeepAlways; [self addAttachment:attachment];
}
- (void)testSplitSelectionRotationAndAnchoredShare {
    [self launchWithArguments:@[]];
    XCUIElement *history = self.app.tables[@"history.table"];
    XCTAssertTrue([history waitForExistenceWithTimeout:5]);
    XCTAssertTrue(self.app.staticTexts[@"scan.result"].exists);
    XCTAssertFalse(self.app.tabBars.firstMatch.exists, @"Native iPad must use the split workflow, not the phone tab shell.");
    XCUIDevice.sharedDevice.orientation = UIDeviceOrientationLandscapeLeft;
    NSPredicate *landscape = [NSPredicate predicateWithBlock:^BOOL(id object, NSDictionary *bindings) { XCUIElement *app = object; return app.frame.size.width > app.frame.size.height; }];
    [self expectationForPredicate:landscape evaluatedWithObject:self.app handler:nil]; [self waitForExpectationsWithTimeout:8 handler:nil];
    XCTAssertTrue(history.hittable);
    [history.cells.firstMatch tap];
    XCTAssertEqualObjects(self.app.staticTexts[@"scan.result"].label, @"Native iPad QR result 你好");
    XCTAssertEqual(history.cells.count, 1);
    XCUIElement *share = self.app.buttons[@"scan.share"];
    if (!share.hittable) [self.app.scrollViews.firstMatch swipeUp];
    XCTAssertTrue(share.hittable); [share tap];
    XCTAssertTrue([self.app.otherElements[@"ActivityListView"] waitForExistenceWithTimeout:5] || self.app.buttons[@"Copy"].exists, @"%@", self.app.debugDescription);
    [self capture:@"ipad-anchored-share"];
    // Dismiss the popover by tapping outside it, retaining the selected payload.
    [history.cells.firstMatch tap];
    XCTAssertEqualObjects(self.app.staticTexts[@"scan.result"].label, @"Native iPad QR result 你好");
    XCUIDevice.sharedDevice.orientation = UIDeviceOrientationPortrait;
    XCTAssertTrue([self.app.buttons[@"scan.import"] waitForExistenceWithTimeout:5]);
    [self capture:@"ipad-split-portrait"];
    [self.app terminate];
    self.app.launchArguments = @[@"-ui-testing", @"-AppleLanguages", @"(en)"];
    [self.app launch];
    XCTAssertTrue([self.app.tables[@"history.table"].cells.firstMatch waitForExistenceWithTimeout:10]);
    [self.app.tables[@"history.table"].cells.firstMatch tap];
    XCTAssertEqualObjects(self.app.staticTexts[@"scan.result"].label, @"Native iPad QR result 你好");
}
- (void)testRealPhotoImportReplacesSelectionAndPreservesBothRecords {
    [self launchWithArguments:@[]];
    XCUIElement *import = self.app.buttons[@"scan.import"];
    if (!import.hittable) { [self.app.scrollViews.firstMatch swipeUp]; [self.app.scrollViews.firstMatch swipeUp]; }
    XCTAssertTrue(import.hittable); [import tap];
    [self.app.buttons[@"Photo Library"] tap];
    // The iPad picker has a sidebar collection before its actual asset grid.
    // Use the real photo-image AX identifier observed in run 37121579198.
    XCUIElement *photo = self.app.images[@"PXGGridLayout-Info"].firstMatch;
    XCTAssertTrue([photo waitForExistenceWithTimeout:45], @"%@", self.app.debugDescription);
    [photo tap];
    NSPredicate *decoded = [NSPredicate predicateWithFormat:@"label == %@", @"QRCatcher 你好 🌈 123"];
    [self expectationForPredicate:decoded evaluatedWithObject:self.app.staticTexts[@"scan.result"] handler:nil];
    [self waitForExpectationsWithTimeout:20 handler:nil];
    XCTAssertEqual(self.app.tables[@"history.table"].cells.count, 2);
    XCTAssertFalse(self.app.buttons[@"scan.open"].exists);
    [self capture:@"ipad-imported-photo"];
    [self.app terminate]; self.app.launchArguments = @[@"-ui-testing", @"-AppleLanguages", @"(en)"]; [self.app launch];
    XCUIElement *records = self.app.tables[@"history.table"];
    XCTAssertTrue([records.cells.firstMatch waitForExistenceWithTimeout:10]);
    XCTAssertEqual(records.cells.count, 2);
    [records.cells.firstMatch tap];
    XCTAssertEqualObjects(self.app.staticTexts[@"scan.result"].label, @"QRCatcher 你好 🌈 123");
    [self capture:@"ipad-imported-photo"];
}
- (void)testLargeTextImportCancellationAndPrivacyReturn {
    [self launchWithArguments:@[@"-UIPreferredContentSizeCategoryName", @"UICTContentSizeCategoryAccessibilityXXXL"]];
    [self.app.scrollViews.firstMatch swipeUp]; [self.app.scrollViews.firstMatch swipeUp];
    XCTAssertTrue(self.app.buttons[@"scan.import"].hittable);
    [self.app.buttons[@"scan.import"] tap];
    XCTAssertTrue([self.app.buttons[@"Photo Library"] waitForExistenceWithTimeout:5]);
    [self.app.buttons[@"Photo Library"] tap];
    XCUIElement *cancel = self.app.buttons[@"Cancel"].firstMatch;
    XCTAssertTrue([cancel waitForExistenceWithTimeout:10]); [cancel tap];
    XCTAssertEqual(self.app.tables[@"history.table"].cells.count, 1);
    [self.app.navigationBars.buttons[@"privacy.policy"].firstMatch tap];
    XCTAssertTrue([self.app.navigationBars.buttons[@"privacy.close"] waitForExistenceWithTimeout:15]);
    [self.app.navigationBars.buttons[@"privacy.close"] tap];
    XCTAssertTrue([self.app.tables[@"history.table"] waitForExistenceWithTimeout:5]);
    [self capture:@"ipad-large-text"];
    XCUIElement *title = self.app.navigationBars[@"History"].staticTexts[@"History"];
    XCTAssertTrue(title.exists, @"History title remains accessible at largest text");
    XCTAssertEqualObjects(title.label, @"History");
    CGFloat minimumWidth = [@"History" sizeWithAttributes:@{NSFontAttributeName:[UIFont boldSystemFontOfSize:17]}].width;
    XCTAssertGreaterThanOrEqual(title.frame.size.width + 0.5, minimumWidth, @"The visible title must fit, not merely expose a complete AX label");
    NSError *error = nil;
    XCTAssertTrue([self.app performAccessibilityAuditWithAuditTypes:XCUIAccessibilityAuditTypeAll issueHandler:nil error:&error], @"iPad largest-text split/result accessibility audit: %@", error);
}
@end
