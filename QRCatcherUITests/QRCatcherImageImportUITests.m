#import <XCTest/XCTest.h>
#import <UIKit/UIKit.h>
#import "QRUIInterruptionSafety.h"
#import "QRFilesPickerSnapshot.h"

static BOOL QRPhoneFilesPresentationSnapshotReady(id<XCUIElementSnapshot> root) {
    if (!root) return NO;
    NSMutableArray<id<XCUIElementSnapshot>> *queue = [NSMutableArray arrayWithObject:root];
    NSMutableArray<NSNumber *> *parents = [NSMutableArray arrayWithObject:@(-1)];
    QRFilesNode nodes[QR_FILES_SNAPSHOT_MAX_NODES];
    for (NSUInteger index = 0; index < queue.count; index++) {
        id<XCUIElementSnapshot> snapshot = queue[index];
        CGRect frame = snapshot.frame;
        QRFilesKind kind = snapshot.elementType == XCUIElementTypeWindow ? QRFilesWindow :
            snapshot.elementType == XCUIElementTypeNavigationBar ? QRFilesNavigationBar :
            snapshot.elementType == XCUIElementTypeButton ? QRFilesButton :
            snapshot.elementType == XCUIElementTypeOther ? QRFilesOther : QRFilesUnknown;
        nodes[index] = (QRFilesNode){parents[index].intValue, kind, snapshot.identifier.UTF8String,
            snapshot.label.UTF8String, snapshot.enabled, {frame.origin.x, frame.origin.y, frame.size.width, frame.size.height}};
        for (id<XCUIElementSnapshot> child in snapshot.children) {
            if (queue.count >= QR_FILES_SNAPSHOT_MAX_NODES) return NO;
            [queue addObject:child]; [parents addObject:@(index)];
        }
    }
    return QRFilesPickerPresentationReady(nodes, queue.count);
}
@interface QRCatcherImageImportUITests : XCTestCase
@property (nonatomic, strong) XCUIApplication *app;
@property (nonatomic, strong) id interruptionGuard;
@property (nonatomic, copy) NSArray *historyRowsBeforePresentation;
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
- (NSDictionary *)auditCurrentResultPhase:(NSString *)phase {
    NSUInteger failuresBefore = self.testRun.failureCount;
    __block NSUInteger callbackIssues = 0;
    NSError *error = nil;
    BOOL apiReturnedSuccess = NO;
    BOOL previousContinuation = self.continueAfterFailure;
    // Only audits continue after their retained failures. Data/navigation
    // assertions outside this method keep their fail-fast behavior.
    self.continueAfterFailure = YES;
    @try {
        if (@available(iOS 17.0, *)) {
            apiReturnedSuccess = [self.app performAccessibilityAuditWithAuditTypes:XCUIAccessibilityAuditTypeAll issueHandler:^BOOL(XCUIAccessibilityAuditIssue *issue) {
                callbackIssues += 1;
                NSLog(@"REAL_IMPORTED_RESULT_AUDIT:%@ %@ %@ PHASE:%@", issue.compactDescription, issue.detailedDescription, issue.element.debugDescription, phase);
                return NO;
            } error:&error];
            XCTAssertTrue(apiReturnedSuccess, @"Real imported/reopened result accessibility audit: %@", error);
            XCTAssertEqual(callbackIssues, 0, @"Every full-audit issue remains a failure");
        } else { XCTFail(@"The strict imported-result audit is unavailable on this runtime"); }
    } @finally { self.continueAfterFailure = previousContinuation; }
    NSDictionary *receipt = @{@"phase": phase, @"callback_issues": @(callbackIssues),
        @"registered_failure_delta": @(self.testRun.failureCount - failuresBefore),
        @"api_returned_success": @(apiReturnedSuccess), @"error": error.localizedDescription ?: @""};
    NSLog(@"REAL_IMPORTED_RESULT_AUDIT_RECEIPT:%@", receipt);
    return receipt; // An API return value alone is never an audit-pass claim.
}
- (void)attachBoundedText:(NSString *)text name:(NSString *)name {
    XCTAssertLessThanOrEqual([text lengthOfBytesUsingEncoding:NSUTF8StringEncoding], 64 * 1024);
    XCTAttachment *attachment = [XCTAttachment attachmentWithString:text];
    attachment.name = name; attachment.lifetime = XCTAttachmentLifetimeKeepAlways; [self addAttachment:attachment];
}
- (void)attachImportAuditTree:(NSString *)name {
    NSString *tree = self.app.debugDescription;
    [self attachBoundedText:[tree substringToIndex:MIN(tree.length, 16000)] name:name];
}
- (NSArray *)importedHistoryRows {
    XCUIElement *table = self.app.tables[@"history.table"];
    XCTAssertEqual(table.cells.count, 2);
    if (table.cells.count != 2) return nil;
    NSMutableArray *rows = [NSMutableArray new];
    for (XCUIElement *cell in table.cells.allElementsBoundByIndex) {
        NSMutableArray *labels = [NSMutableArray new];
        for (XCUIElement *text in cell.staticTexts.allElementsBoundByIndex) [labels addObject:text.label];
        [rows addObject:labels];
    }
    XCTAssertTrue(table.cells.firstMatch.staticTexts[@"QRCatcher 你好 🌈 123"].exists);
    XCTAssertTrue([table.cells elementBoundByIndex:1].staticTexts[@"Previous selected result"].exists);
    return rows;
}
- (void)auditCurrentResult {
    if (UIDevice.currentDevice.userInterfaceIdiom != UIUserInterfaceIdiomPhone) {
        [self auditCurrentResultPhase:@"selected-result"]; return;
    }
    XCUIElement *result = self.app.otherElements[@"history.result"];
    XCUIElement *body = result.staticTexts[@"history.result.payload"];
    XCTAssertTrue(result.exists && [body.label isEqualToString:@"QRCatcher 你好 🌈 123"]);
    if (!result.exists || ![body.label isEqualToString:@"QRCatcher 你好 🌈 123"]) return;
    NSArray *before = self.historyRowsBeforePresentation;
    XCTAssertNotNil(before, @"Retain the actual saved rows before full-screen presentation");
    if (!before) return;
    [self attachBoundedText:@"phone-result-history" name:@"image-import-audit-pair-required"];
    [self attachImportAuditTree:@"image-import-result-audit-tree"];
    NSDictionary *first = [self auditCurrentResultPhase:@"app-owned-result"];
    // Only this exact app-owned result may supply Cancel. System permission
    // dialogs remain native, and must never be dismissed by this action.
    XCUIElement *cancel = result.buttons[@"history.result.cancel"];
    BOOL canCancel = result.exists && [body.label isEqualToString:@"QRCatcher 你好 🌈 123"] &&
                     cancel.exists && cancel.enabled && cancel.hittable;
    XCTAssertTrue(canCancel, @"The original app-owned QR result must own an available Cancel");
    if (!canCancel) return;
    [cancel tap];
    XCTNSPredicateExpectation *closed = [[XCTNSPredicateExpectation alloc] initWithPredicate:[NSPredicate predicateWithFormat:@"exists == NO"] object:result];
    XCTWaiterResult closeResult = [XCTWaiter waitForExpectations:@[closed] timeout:10];
    XCTAssertEqual(closeResult, XCTWaiterResultCompleted);
    if (closeResult != XCTWaiterResultCompleted) return;
    NSArray *after = [self importedHistoryRows];
    XCTAssertEqualObjects(after, before, @"Cancel must preserve the same payload/date rows before the second audit");
    if (![after isEqual:before]) return;
    [self capture:@"image-import-history-after-cancel"];
    [self attachImportAuditTree:@"image-import-history-audit-tree"];
    NSDictionary *second = [self auditCurrentResultPhase:@"same-history-after-cancel"];
    NSData *data = [NSJSONSerialization dataWithJSONObject:@[first, second] options:0 error:nil];
    XCTAssertNotNil(data);
    if (!data) return;
    [self attachBoundedText:[[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] name:@"image-import-audit-pair-receipts"];
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
        if (item.exists && item.enabled && item.hittable) return item;
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
    if (phone) self.historyRowsBeforePresentation = [self importedHistoryRows];
    [table.cells.firstMatch tap];
    if (phone) {
        // Phone history uses its app-owned detail; the iPad split callback
        // still replaces only the selected scanner result.
        XCUIElement *result=self.app.otherElements[@"history.result"];
        XCTAssertTrue([result waitForExistenceWithTimeout:10]);
        XCTAssertEqualObjects(result.staticTexts[@"history.result.payload"].label,@"QRCatcher 你好 🌈 123");
        XCTAssertTrue(result.buttons[@"history.result.copy"].hittable);
        XCTAssertFalse(result.buttons[@"history.result.open"].exists);
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
    if (UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPhone) {
        // One immutable public snapshot classifies the exact native context.
        // This avoids separate remote resolutions consuming six to seven
        // seconds after the picker appeared on both observed phone profiles.
        // Classification performs no action and is not a hittability claim;
        // each subsequent real action resolves fresh enabled/hittable state.
        NSPredicate *pickerReady = [NSPredicate predicateWithBlock:^BOOL(id object, NSDictionary *bindings) {
            XCUIApplication *app = object;
            NSError *error = nil;
            id<XCUIElementSnapshot> snapshot = [app snapshotWithError:&error];
            return snapshot && !error && QRPhoneFilesPresentationSnapshotReady(snapshot);
        }];
        XCTNSPredicateExpectation *ready = [[XCTNSPredicateExpectation alloc] initWithPredicate:pickerReady object:self.app];
        XCTWaiterResult outcome = [XCTWaiter waitForExpectations:@[ready] timeout:20];
        XCTAssertEqual(outcome, XCTWaiterResultCompleted,
                       @"Expected the observed native Files picker and its available Cancel control: %@", self.app.debugDescription);
        if (outcome != XCTWaiterResultCompleted) return;
    } else {
        XCTAssertTrue([self.app.buttons[@"Cancel"].firstMatch waitForExistenceWithTimeout:20],@"%@",self.app.debugDescription);
    }
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
