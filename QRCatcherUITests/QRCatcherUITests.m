#import <XCTest/XCTest.h>
#import <UIKit/UIKit.h>

/// Capture-only test target. The shipping application tree is unchanged from the frozen release candidate.
@interface QRCatcherUITests : XCTestCase
@property (nonatomic, strong) XCUIApplication *app;
@end
@implementation QRCatcherUITests
- (void)setUp {
    [super setUp];
    self.continueAfterFailure = NO;
    self.app = [XCUIApplication new];
    XCUIDevice.sharedDevice.orientation = UIDeviceOrientationPortrait;
}
- (void)launchWithPayload:(NSString *)payload reset:(BOOL)reset {
    NSMutableArray *arguments = [@[@"-ui-testing", @"-AppleLanguages", @"(zh-Hans)", @"-AppleLocale", @"zh_CN", @"-fixture-payload", payload] mutableCopy];
    if (reset) [arguments addObject:@"-reset-history"];
    self.app.launchArguments = arguments;
    [self.app launch];
    XCTAssertTrue([self.app.staticTexts[@"scan.result"] waitForExistenceWithTimeout:15]);
    XCTAssertEqualObjects(self.app.staticTexts[@"scan.result"].label, payload);
}
- (void)captureScreen:(NSString *)name {
    UIImage *image = XCUIScreen.mainScreen.screenshot.image;
    XCTAssertEqual(CGImageGetWidth(image.CGImage), 1320);
    XCTAssertEqual(CGImageGetHeight(image.CGImage), 2868);
    NSData *JPEG = UIImageJPEGRepresentation(image, 0.88);
    XCTAssertNotNil(JPEG);
    XCTAssertLessThanOrEqual(JPEG.length, 1024 * 1024);
    if (!JPEG || JPEG.length > 1024 * 1024) return;
    NSString *base64 = [JPEG base64EncodedStringWithOptions:0];
    NSLog(@"SCREENSHOT_METADATA:%@ pixels=1320x2868 format=JPEG bytes=%lu seeded_qr=YES live_camera=NO", name, (unsigned long)JPEG.length);
    NSLog(@"SCREENSHOT_BEGIN:%@", name);
    for (NSUInteger index = 0; index < base64.length; index += 4096) {
        NSLog(@"SCREENSHOT_CHUNK:%@", [base64 substringWithRange:NSMakeRange(index, MIN((NSUInteger)4096, base64.length-index))]);
    }
    NSLog(@"SCREENSHOT_END:%@", name);
}
- (void)testCaptureStoreScreenshots {
    // Public/synthetic sample QR content only. No camera feed or marketing overlay is fabricated.
    [self launchWithPayload:@"https://100mango.github.io/" reset:YES];
    XCTAssertTrue(self.app.buttons[@"scan.open"].exists);
    [self captureScreen:@"store-01-scan-result-zh-Hans"];

    [self.app terminate];
    [self launchWithPayload:@"你好，QRCatcher" reset:NO];
    [self.app terminate];
    [self launchWithPayload:@"https://100mango.github.io/app-privacy/" reset:NO];
    [self.app.tabBars.buttons[@"history.tab"] tap];
    XCTAssertTrue([self.app.tables.cells.staticTexts[@"你好，QRCatcher"] waitForExistenceWithTimeout:10]);
    XCTAssertEqual(self.app.tables.cells.count, 3);
    [self captureScreen:@"store-02-history-zh-Hans"];

    [self.app.tables.cells.staticTexts[@"https://100mango.github.io/"] tap];
    XCTAssertTrue([self.app.alerts.buttons[@"打开网页"] waitForExistenceWithTimeout:5]);
    XCTAssertTrue(self.app.alerts.buttons[@"复制内容"].exists);
    [self captureScreen:@"store-03-history-detail-zh-Hans"];
    [self.app.alerts.buttons[@"取消"] tap];

    [self.app.navigationBars.buttons[@"privacy.policy"] tap];
    XCTAssertTrue([self.app.navigationBars.buttons[@"privacy.close"] waitForExistenceWithTimeout:10]);
    XCUIElement *heading = self.app.webViews.staticTexts[@"应用隐私政策"].firstMatch;
    XCTAssertTrue([heading waitForExistenceWithTimeout:30], @"The approved policy must actually load before capture. %@", self.app.debugDescription);
    [self captureScreen:@"store-04-privacy-policy-zh-Hans"];
    [self.app.navigationBars.buttons[@"privacy.close"] tap];
    XCTAssertTrue([self.app.tables[@"history.table"] waitForExistenceWithTimeout:5]);
    XCTAssertEqual(self.app.tables.cells.count, 3);
}
@end
