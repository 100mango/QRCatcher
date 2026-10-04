#import <XCTest/XCTest.h>
#import <UIKit/UIKit.h>
#import "QRUIInterruptionSafety.h"
@interface QRCatcherImageImportUITests : XCTestCase
@property (nonatomic, strong) XCUIApplication *app;
@property (nonatomic, strong) id interruptionGuard;
@end
@implementation QRCatcherImageImportUITests
- (void)setUp {
    [super setUp]; self.continueAfterFailure = NO;
    self.interruptionGuard = QRInstallFailClosedInterruptionMonitor(self);
    self.app = [XCUIApplication new];
    self.app.launchArguments = @[@"-ui-testing",@"-reset-history",@"-AppleLanguages",@"(en)",@"-AppleLocale",@"en_US",@"-fixture-payload",@"Previous selected result"];
    [self.app launch]; XCTAssertTrue([self.app.staticTexts[@"scan.result"] waitForExistenceWithTimeout:15]);
}
- (void)tearDown {
    if (self.testRun.failureCount) { NSLog(@"ACTUAL_IMAGE_IMPORT_UI:%@",self.app.debugDescription); [self capture:@"image-import-failure"]; }
    [self.app terminate]; [super tearDown];
    [self removeUIInterruptionMonitor:self.interruptionGuard];
}
- (void)capture:(NSString *)name {
    NSData *data = UIImageJPEGRepresentation(XCUIScreen.mainScreen.screenshot.image,0.45);
    XCTAssertLessThanOrEqual(data.length,800*1024);
    XCTAttachment *attachment = [XCTAttachment attachmentWithData:data uniformTypeIdentifier:@"public.jpeg"];
    attachment.name=name; attachment.lifetime=XCTAttachmentLifetimeKeepAlways; [self addAttachment:attachment];
}
- (void)auditCurrentResult {
    if (@available(iOS 17.0, *)) {
        NSError *error=nil;
        BOOL passed=[self.app performAccessibilityAuditWithAuditTypes:XCUIAccessibilityAuditTypeAll issueHandler:^BOOL(XCUIAccessibilityAuditIssue *issue) {
            NSLog(@"REAL_IMPORTED_RESULT_AUDIT:%@ %@ %@",issue.compactDescription,issue.detailedDescription,issue.element.debugDescription);
            return NO;
        } error:&error];
        XCTAssertTrue(passed,@"Real imported/reopened result accessibility audit: %@",error);
    }
}
- (void)chooseSource:(NSString *)title {
    XCUIElement *button=self.app.buttons[@"scan.import"];
    for (NSUInteger i=0;i<3 && !button.hittable;i++) [self.app.scrollViews.firstMatch swipeUp];
    XCTAssertTrue(button.hittable); [button tap];
    XCTAssertTrue([self.app.buttons[title] waitForExistenceWithTimeout:5]); [self.app.buttons[title] tap];
}
- (XCUIElement *)visibleItem:(NSString *)name {
    // Resolve by current semantic identity. Index-bound arrays become stale
    // while the real document picker finishes loading its controls.
    NSPredicate *match=[NSPredicate predicateWithFormat:@"label == %@ OR identifier == %@ OR label BEGINSWITH %@",name,name,[name stringByAppendingString:@","]];
    for (XCUIElementQuery *query in @[self.app.cells,self.app.buttons,self.app.staticTexts]) {
        XCUIElement *item=[query matchingPredicate:match].firstMatch;
        if (item.exists && item.hittable) return item;
    }
    return nil;
}
- (void)tapVisibleItem:(NSString *)name {
    XCUIElement *item=nil;
    for (NSUInteger i=0;i<20 && !item;i++) { item=[self visibleItem:name]; if(!item)[NSThread sleepForTimeInterval:0.5]; }
    XCTAssertNotNil(item,@"Expected %@ in actual Files UI: %@",name,self.app.debugDescription); [item tap];
}
- (void)assertImportedResultAndRelaunch {
    NSPredicate *decoded=[NSPredicate predicateWithFormat:@"label == %@",@"QRCatcher 你好 🌈 123"];
    [self expectationForPredicate:decoded evaluatedWithObject:self.app.staticTexts[@"scan.result"] handler:nil]; [self waitForExpectationsWithTimeout:20 handler:nil];
    XCTAssertFalse(self.app.buttons[@"scan.open"].exists);
    [self capture:[self.name containsString:@"Files"] ? @"image-import-files-decoded" : @"image-import-photos-decoded"];
    [self.app terminate]; self.app.launchArguments=@[@"-ui-testing",@"-AppleLanguages",@"(en)"]; [self.app launch];
    BOOL phone=UIDevice.currentDevice.userInterfaceIdiom==UIUserInterfaceIdiomPhone;
    XCTAssertEqual(self.app.tabBars.firstMatch.exists,phone,@"The expected phone/tab and iPad/split routes must stay distinct");
    if (phone) [self.app.tabBars.buttons[@"History"] tap];
    XCUIElement *table=self.app.tables[@"history.table"];
    XCTAssertTrue([table.cells.firstMatch waitForExistenceWithTimeout:10]); XCTAssertEqual(table.cells.count,2);
    XCTAssertTrue(table.cells.firstMatch.staticTexts[@"QRCatcher 你好 🌈 123"].exists);
    [table.cells.firstMatch tap];
    if (phone) {
        // Preserve the established phone history alert, rather than expecting
        // the iPad split-view selection callback to replace the scanner.
        XCUIElement *result=self.app.alerts[@"QR Code"];
        XCTAssertTrue([result waitForExistenceWithTimeout:10]);
        XCTAssertTrue(result.staticTexts[@"QRCatcher 你好 🌈 123"].exists);
        XCTAssertTrue(result.buttons[@"Copy Result"].hittable);
        XCTAssertFalse(result.buttons[@"Open Website"].exists);
    } else {
        XCTAssertTrue([self.app.staticTexts[@"scan.result"] waitForExistenceWithTimeout:10]);
        XCTAssertEqualObjects(self.app.staticTexts[@"scan.result"].label,@"QRCatcher 你好 🌈 123");
    }
}
- (void)testRealPickerWarmupAndCancelPreservesPreviousSelection {
    [self chooseSource:@"Photo Library"];
    XCUIElement *cancel=self.app.buttons[@"Cancel"].firstMatch;
    XCTAssertTrue([cancel waitForExistenceWithTimeout:20]); [cancel tap];
    XCTAssertEqualObjects(self.app.staticTexts[@"scan.result"].label,@"Previous selected result");
}
- (void)testRealPhotosImportAndReopen {
    [self chooseSource:@"Photo Library"];
    XCUIElement *photo=self.app.images[@"PXGGridLayout-Info"].firstMatch;
    XCTAssertTrue([photo waitForExistenceWithTimeout:30],@"%@",self.app.debugDescription); [photo tap];
    [self assertImportedResultAndRelaunch]; [self capture:@"image-import-real-photos"]; [self auditCurrentResult];
}
- (void)testRealFilesImportAndReopen {
    [self chooseSource:@"Choose File"];
    XCTAssertTrue([self.app.buttons[@"Cancel"].firstMatch waitForExistenceWithTimeout:20],@"%@",self.app.debugDescription);
    if (![self visibleItem:@"QRCatcher-Test-Imports"]) {
        XCUIElement *browse=[self visibleItem:@"Browse"]; if(browse)[browse tap];
        NSString *location=UIDevice.currentDevice.userInterfaceIdiom==UIUserInterfaceIdiomPad ? @"On My iPad" : @"On My iPhone";
        if (![self visibleItem:@"QRCatcher"]) [self tapVisibleItem:location];
        [self tapVisibleItem:@"QRCatcher"];
    }
    [self tapVisibleItem:@"QRCatcher-Test-Imports"];
    if ([self visibleItem:@"SyntheticQR.png"]) [self tapVisibleItem:@"SyntheticQR.png"];
    else [self tapVisibleItem:@"SyntheticQR"];
    [self assertImportedResultAndRelaunch]; [self capture:@"image-import-real-files"]; [self auditCurrentResult];
}
@end
