#import <XCTest/XCTest.h>
#import <UIKit/UIKit.h>
// Smoke test of the older XCTest infrastructure only; no app feature coverage.
@interface OldRuntimeAppTests : XCTestCase @end
@implementation OldRuntimeAppTests
- (void)testHarnessWindow {
    self.continueAfterFailure=NO; self.executionTimeAllowance=180;
    XCTAssertEqualObjects(UIDevice.currentDevice.systemVersion,@"15.5");
    XCUIDevice.sharedDevice.orientation=UIDeviceOrientationPortrait;
    XCUIApplication *app=[[XCUIApplication alloc] initWithBundleIdentifier:@"test.cloud.compatibility.CompatibilityHarnessHost"];
    [app launch];
    XCUIElement *button=app.buttons[@"harness.check"];
    XCTAssertTrue([button waitForExistenceWithTimeout:30]);
    XCTAssertTrue(button.hittable); XCTAssertTrue(CGRectContainsRect(app.frame,button.frame));
    CGFloat width=app.frame.size.width;
    XCTAssertTrue(fabs(width-320)<1 || fabs(width-768)<1,@"Unexpected smallest-device viewport: %@",NSStringFromCGRect(app.frame));
    [button tap]; XCTAssertEqualObjects(app.staticTexts[@"harness.status"].label,@"Interaction verified");
    [XCUIDevice.sharedDevice pressButton:XCUIDeviceButtonHome]; [app activate];
    XCTAssertEqualObjects(app.staticTexts[@"harness.status"].label,@"Interaction verified");
    NSLog(@"OLDEST_HARNESS_ONLY_PASS runtime=%@ viewport=%@ app_feature_tests=0",UIDevice.currentDevice.systemVersion,NSStringFromCGRect(app.frame));
    [app terminate];
}
@end
