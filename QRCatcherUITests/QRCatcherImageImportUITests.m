#import <XCTest/XCTest.h>
#import <UIKit/UIKit.h>
@interface QRCatcherImageImportUITests : XCTestCase
@property (nonatomic, strong) XCUIApplication *app;
@end
@implementation QRCatcherImageImportUITests
- (void)setUp {
    [super setUp]; self.continueAfterFailure = NO; self.app = [XCUIApplication new];
    self.app.launchArguments = @[@"-ui-testing",@"-reset-history",@"-AppleLanguages",@"(en)",@"-AppleLocale",@"en_US",@"-fixture-payload",@"Previous selected result"];
    [self.app launch]; XCTAssertTrue([self.app.staticTexts[@"scan.result"] waitForExistenceWithTimeout:15]);
}
- (void)tearDown {
    if (self.testRun.failureCount) { NSLog(@"ACTUAL_IMAGE_IMPORT_UI:%@",self.app.debugDescription); [self capture:@"image-import-failure"]; }
    [self.app terminate]; [super tearDown];
}
- (void)capture:(NSString *)name {
    NSData *data = UIImageJPEGRepresentation(XCUIScreen.mainScreen.screenshot.image,0.45);
    XCTAssertLessThanOrEqual(data.length,800*1024);
    XCTAttachment *attachment = [XCTAttachment attachmentWithData:data uniformTypeIdentifier:@"public.jpeg"];
    attachment.name=name; attachment.lifetime=XCTAttachmentLifetimeKeepAlways; [self addAttachment:attachment];
}
- (void)chooseSource:(NSString *)title {
    XCUIElement *button=self.app.buttons[@"scan.import"];
    for (NSUInteger i=0;i<3 && !button.hittable;i++) [self.app.scrollViews.firstMatch swipeUp];
    XCTAssertTrue(button.hittable); [button tap];
    XCTAssertTrue([self.app.buttons[title] waitForExistenceWithTimeout:5]); [self.app.buttons[title] tap];
}
- (XCUIElement *)visibleItem:(NSString *)name {
    // Only observed, visible UI names inside the real document picker are used.
    for (XCUIElementQuery *query in @[self.app.cells,self.app.buttons,self.app.staticTexts]) {
        for (XCUIElement *item in query.allElementsBoundByIndex) {
            BOOL named=[item.label isEqualToString:name] || [item.identifier isEqualToString:name] || [item.label hasPrefix:[name stringByAppendingString:@","]];
            if (named && item.hittable) return item;
        }
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
    [self.app terminate]; self.app.launchArguments=@[@"-ui-testing",@"-AppleLanguages",@"(en)"]; [self.app launch];
    if (self.app.tabBars.firstMatch.exists) [self.app.tabBars.buttons[@"History"] tap];
    XCUIElement *table=self.app.tables[@"history.table"];
    XCTAssertTrue([table.cells.firstMatch waitForExistenceWithTimeout:10]); XCTAssertEqual(table.cells.count,2);
    [table.cells.firstMatch tap]; XCTAssertTrue([self.app.staticTexts[@"scan.result"] waitForExistenceWithTimeout:10]);
    XCTAssertEqualObjects(self.app.staticTexts[@"scan.result"].label,@"QRCatcher 你好 🌈 123");
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
    [self assertImportedResultAndRelaunch]; [self capture:@"image-import-real-photos"];
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
    [self assertImportedResultAndRelaunch]; [self capture:@"image-import-real-files"];
}
@end
