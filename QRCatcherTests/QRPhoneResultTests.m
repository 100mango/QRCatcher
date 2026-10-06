#import <XCTest/XCTest.h>
#include <math.h>
#import "QRPhoneResultViewController.h"
#import "QRURLViewController.h"
#import "QRCatchViewController.h"
#import "AppDelegate.h"
#import "QRHistoryStore.h"
#import "QRImageCodec.h"
#import "URLEntity.h"

@interface QRPhoneResultViewController (ResultTesting)
- (void)cancel;
- (void)copyResult;
- (void)openWebsite;
@end
@interface QRCatchViewController (PhoneResultTesting)
- (void)handlePayload:(NSString *)payload;
@end

/// This double records UIKit transport, not dismissal animation behavior.
@interface QRRecordedPhoneResult : QRPhoneResultViewController
@property (nonatomic) NSUInteger dismissalCount;
@property (nonatomic, copy) void (^pendingDismissal)(void);
@end
@implementation QRRecordedPhoneResult
- (void)dismissViewControllerAnimated:(BOOL)animated completion:(void (^)(void))completion {
    self.dismissalCount += 1; self.pendingDismissal = completion;
}
@end
@interface QRRecordedHistoryPresenter : QRURLViewController
@property (nonatomic, strong) UIViewController *recordedPresentation;
@property (nonatomic) NSUInteger presentationCount;
@end
@implementation QRRecordedHistoryPresenter
- (UIViewController *)presentedViewController { return self.recordedPresentation; }
- (void)presentViewController:(UIViewController *)controller animated:(BOOL)animated completion:(void (^)(void))completion {
    self.recordedPresentation = controller; self.presentationCount += 1;
    if (completion) completion();
}
@end

@interface QRPhoneResultTests : XCTestCase
@end
@implementation QRPhoneResultTests
- (UIView *)ownedView:(NSString *)identifier inView:(UIView *)view {
    // Read only app-owned views via public UIView properties. No KVC or UIKit
    // alert hierarchy is involved in either product code or these tests.
    if ([view.accessibilityIdentifier isEqualToString:identifier]) return view;
    for (UIView *child in view.subviews) {
        UIView *found = [self ownedView:identifier inView:child];
        if (found) return found;
    }
    return nil;
}
- (void)finishRecordedDismissal:(QRRecordedPhoneResult *)result {
    void (^completion)(void) = result.pendingDismissal;
    result.pendingDismissal = nil;
    if (completion) completion();
}
- (void)testCompleteUnicodeSnapshotCopiesOnceOnlyAfterDismissal {
    NSMutableString *payload = [NSMutableString stringWithString:@"  首行 👩🏽‍💻 e\u0301\n"];
    for (NSUInteger index = 0; index < 80; index++) [payload appendString:@"完整内容 🌈 العربية עברית \n"];
    [payload appendString:@"最后一行 END  \n"];
    NSString *expected = [payload copy];
    NSArray *oldPasteboard = UIPasteboard.generalPasteboard.items;
    @try {
        UIPasteboard.generalPasteboard.string = @"unchanged before dismissal";
        QRRecordedPhoneResult *result = [[QRRecordedPhoneResult alloc] initWithPayload:payload openWebsiteHandler:^(NSURL *URL) { XCTFail(@"Text cannot open a URL"); }];
        [payload appendString:@"mutation must not change the snapshot"];
        [result loadViewIfNeeded];
        UILabel *body = (UILabel *)[self ownedView:@"history.result.payload" inView:result.view];
        XCTAssertEqualObjects(result.payload, expected); XCTAssertEqualObjects(body.text, expected);
        XCTAssertEqual(body.numberOfLines, 0); XCTAssertTrue(body.adjustsFontForContentSizeCategory);
        XCTAssertNil([self ownedView:@"history.result.open" inView:result.view]);
        [result copyResult]; [result copyResult]; [result cancel];
        XCTAssertEqual(result.dismissalCount, 1);
        XCTAssertEqualObjects(UIPasteboard.generalPasteboard.string, @"unchanged before dismissal");
        [self finishRecordedDismissal:result];
        XCTAssertEqualObjects(UIPasteboard.generalPasteboard.string, expected);
    } @finally { UIPasteboard.generalPasteboard.items = oldPasteboard; }
}
- (void)testCancelAndAccessibilityEscapeHaveNoCopyOrOpenSideEffects {
    NSArray *oldPasteboard = UIPasteboard.generalPasteboard.items;
    @try {
        UIPasteboard.generalPasteboard.string = @"preserved clipboard";
        for (NSUInteger cycle = 0; cycle < 3; cycle++) {
            QRRecordedPhoneResult *result = [[QRRecordedPhoneResult alloc] initWithPayload:@"https://example.com/cancel" openWebsiteHandler:^(NSURL *URL) { XCTFail(@"Cancel must never open"); }];
            [result loadViewIfNeeded];
            if (cycle == 1) XCTAssertTrue([result accessibilityPerformEscape]); else [result cancel];
            [result copyResult]; [result openWebsite]; [result cancel];
            XCTAssertEqual(result.dismissalCount, 1);
            [self finishRecordedDismissal:result];
            XCTAssertEqualObjects(UIPasteboard.generalPasteboard.string, @"preserved clipboard");
        }
    } @finally { UIPasteboard.generalPasteboard.items = oldPasteboard; }
}
- (void)testOnlySafeWebsitesOpenOnceAfterExplicitActionAndDismissal {
    for (NSString *payload in @[@"https://example.com/path?q=one", @"http://example.com", @"example.com/path"]) {
        __block NSUInteger opens = 0; __block NSURL *opened = nil;
        QRRecordedPhoneResult *result = [[QRRecordedPhoneResult alloc] initWithPayload:payload openWebsiteHandler:^(NSURL *URL) { opens += 1; opened = URL; }];
        [result loadViewIfNeeded];
        XCTAssertNotNil([self ownedView:@"history.result.open" inView:result.view]);
        XCTAssertEqual(opens, 0);
        [result openWebsite]; [result openWebsite]; [result copyResult];
        XCTAssertEqual(opens, 0); XCTAssertEqual(result.dismissalCount, 1);
        [self finishRecordedDismissal:result];
        XCTAssertEqual(opens, 1); XCTAssertNotNil(opened.host);
        XCTAssertTrue(([@[@"http", @"https"] containsObject:opened.scheme]));
    }
    for (NSString *payload in @[@"javascript:alert(1)", @"file:///secret", @"tel:123", @"https://user:pass@example.com", @"ordinary text 你好"]) {
        QRRecordedPhoneResult *result = [[QRRecordedPhoneResult alloc] initWithPayload:payload openWebsiteHandler:^(NSURL *URL) { XCTFail(@"Unsafe/text payload cannot open"); }];
        [result loadViewIfNeeded];
        XCTAssertNil([self ownedView:@"history.result.open" inView:result.view]);
        [result openWebsite]; XCTAssertEqual(result.dismissalCount, 0);
    }
}
- (NSArray *)savedRows:(QRHistoryStore *)store {
    NSFetchRequest *request = [NSFetchRequest fetchRequestWithEntityName:@"URLEntity"];
    request.sortDescriptors = @[[NSSortDescriptor sortDescriptorWithKey:@"createDate" ascending:NO]];
    NSMutableArray *rows = [NSMutableArray new];
    for (URLEntity *record in [store.context executeFetchRequest:request error:nil])
        [rows addObject:@[record.url ?: @"", record.createDate ?: NSNull.null]];
    return rows;
}
- (void)testRepeatedDecodedImportsHistorySelectionAndIPadCallbackPreserveRows {
    QRHistoryStore *oldStore = AppDelegate.appDelegate.historyStore;
    @try {
        QRHistoryStore *store = [[QRHistoryStore alloc] initWithURL:nil];
        AppDelegate.appDelegate.historyStore = store;
        XCTAssertTrue([store recordPayload:@"Previous selected result" error:nil]);
        NSData *image = [NSData dataWithContentsOfURL:[[NSBundle bundleForClass:self.class] URLForResource:@"unicode" withExtension:@"png"]];
        NSString *decoded = [QRImageCodec decodeImageData:image error:nil].firstObject;
        XCTAssertEqualObjects(decoded, @"QRCatcher 你好 🌈 123");
        QRCatchViewController *scanner = [QRCatchViewController new]; [scanner loadViewIfNeeded];
        // Actual decoder and scanner save path. Picker/provider lifecycle is
        // independently covered by existing real import and bounded-I/O tests.
        [scanner handlePayload:decoded];
        NSArray *before = [self savedRows:store]; XCTAssertEqual(before.count, 2);
        [scanner handlePayload:decoded]; [scanner handlePayload:decoded];
        XCTAssertEqualObjects([self savedRows:store], before);
        QRRecordedHistoryPresenter *history = [QRRecordedHistoryPresenter new];
        [history loadViewIfNeeded]; UITableView *table = (UITableView *)history.view;
        NSIndexPath *first = [NSIndexPath indexPathForRow:0 inSection:0];
        [table.delegate tableView:table didSelectRowAtIndexPath:first];
        QRPhoneResultViewController *result = (QRPhoneResultViewController *)history.recordedPresentation;
        XCTAssertTrue([result isKindOfClass:QRPhoneResultViewController.class]); XCTAssertEqualObjects(result.payload, decoded);
        [table.delegate tableView:table didSelectRowAtIndexPath:first];
        XCTAssertEqual(history.presentationCount, 1, @"An existing modal cannot be replaced by repeated selection");
        history.recordedPresentation = nil;
        [table.delegate tableView:table didSelectRowAtIndexPath:first];
        XCTAssertEqual(history.presentationCount, 2); XCTAssertNotEqual(history.recordedPresentation, result);
        XCTAssertEqualObjects([self savedRows:store], before);
        __block NSString *selected = nil;
        history.recordedPresentation = nil;
        history.selectedPayloadHandler = ^(NSString *payload) { selected = payload; };
        [table.delegate tableView:table didSelectRowAtIndexPath:first];
        XCTAssertEqualObjects(selected, decoded); XCTAssertEqual(history.presentationCount, 2);
        XCTAssertNil(history.recordedPresentation); XCTAssertEqualObjects([self savedRows:store], before);
    } @finally { AppDelegate.appDelegate.historyStore = oldStore; }
}
// Keep strict containment of the original content target; only the public
// scroll request gains one physical pixel of vertical room inside known padding.
- (void)scrollOriginalRectWithOnePixelMargin:(CGRect)original inScroll:(UIScrollView *)scroll {
    CGFloat scale = scroll.traitCollection.displayScale;
    BOOL scaleValid = isfinite(scale) && scale >= 1;
    XCTAssertTrue(scaleValid, @"A finite actual display scale is required");
    if (!scaleValid) return;
    CGFloat margin = 1.0 / scale;
    CGRect request = CGRectInset(original, 0, -margin);
    BOOL fits = isfinite(margin) && margin > 0 && margin <= 1 &&
        isfinite(request.origin.x) && isfinite(request.origin.y) &&
        isfinite(request.size.width) && isfinite(request.size.height) &&
        request.size.width > 0 && request.size.height > 0 &&
        request.size.width <= scroll.bounds.size.width && request.size.height <= scroll.bounds.size.height &&
        CGRectGetMinX(request) >= 0 && CGRectGetMinY(request) >= 0 &&
        CGRectGetMaxX(request) <= scroll.contentSize.width && CGRectGetMaxY(request) <= scroll.contentSize.height;
    XCTAssertTrue(fits, @"The one-pixel request must fit both viewport and available content padding");
    if (!fits) return;
    [scroll scrollRectToVisible:request animated:NO];
}
- (void)testLargestDynamicTypeFullTextAndActionsInBoundedPublicScrollPanes {
    NSMutableString *payload = [NSMutableString stringWithString:@"BEGIN 👩🏽‍💻 e\u0301 你好\n"];
    for (NSUInteger index = 0; index < 80; index++) [payload appendString:@"Long readable Arabic العربية Hebrew עברית 🌈\n"];
    [payload appendString:@"最后一行 END"];
    NSMutableString *website = [NSMutableString stringWithString:@"https://example.com/"];
    for (NSUInteger index = 0; index < 80; index++) [website appendString:@"long-readable-unicode-你好/"];
    for (NSString *completePayload in @[payload, website]) {
        for (NSValue *value in @[[NSValue valueWithCGSize:CGSizeMake(320,568)], [NSValue valueWithCGSize:CGSizeMake(375,667)], [NSValue valueWithCGSize:CGSizeMake(440,956)], [NSValue valueWithCGSize:CGSizeMake(568,320)]]) {
            UIViewController *host = [UIViewController new]; host.view.frame = (CGRect){CGPointZero, value.CGSizeValue};
            QRPhoneResultViewController *result = [[QRPhoneResultViewController alloc] initWithPayload:completePayload openWebsiteHandler:^(NSURL *URL) { XCTFail(@"Layout does not open websites"); }];
            [host addChildViewController:result];
            UITraitCollection *traits = [UITraitCollection traitCollectionWithPreferredContentSizeCategory:UIContentSizeCategoryAccessibilityExtraExtraExtraLarge];
            [host setOverrideTraitCollection:traits forChildViewController:result];
            [traits performAsCurrentTraitCollection:^{
                [result loadViewIfNeeded]; result.view.frame = host.view.bounds;
                [host.view addSubview:result.view]; [result didMoveToParentViewController:host];
            }];
            [host.view layoutIfNeeded]; [result.view layoutIfNeeded];
            UIScrollView *text = (UIScrollView *)[self ownedView:@"history.result.text-scroll" inView:result.view];
            UIScrollView *actions = (UIScrollView *)[self ownedView:@"history.result.action-scroll" inView:result.view];
            UILabel *body = (UILabel *)[self ownedView:@"history.result.payload" inView:result.view];
            UILabel *title = (UILabel *)[self ownedView:@"history.result.title" inView:result.view];
            XCTAssertEqualObjects(body.text, completePayload); XCTAssertGreaterThan(body.font.pointSize, 17);
            XCTAssertTrue(title.adjustsFontForContentSizeCategory); XCTAssertTrue(body.adjustsFontForContentSizeCategory);
            XCTAssertGreaterThan(text.bounds.size.height, 0); XCTAssertGreaterThan(actions.bounds.size.height, 0);
            XCTAssertTrue(CGRectContainsRect(result.view.bounds, text.frame)); XCTAssertTrue(CGRectContainsRect(result.view.bounds, actions.frame));
            XCTAssertLessThanOrEqual(CGRectGetMaxY(text.frame), CGRectGetMinY(actions.frame));
            CGSize fullText = [body sizeThatFits:CGSizeMake(body.bounds.size.width, CGFLOAT_MAX)];
            XCTAssertGreaterThanOrEqual(body.bounds.size.height + 0.5, fullText.height);
            CGRect fullBody = [body convertRect:body.bounds toView:text];
            CGFloat endpointHeight = body.font.lineHeight;
            CGRect beginning = CGRectMake(fullBody.origin.x, fullBody.origin.y, fullBody.size.width, endpointHeight);
            [self scrollOriginalRectWithOnePixelMargin:beginning inScroll:text];
            XCTAssertTrue(CGRectContainsRect(text.bounds, beginning));
            CGRect ending = CGRectMake(fullBody.origin.x, CGRectGetMaxY(fullBody)-endpointHeight, fullBody.size.width, endpointHeight);
            [self scrollOriginalRectWithOnePixelMargin:ending inScroll:text];
            XCTAssertTrue(CGRectContainsRect(text.bounds, ending));
            CGPoint readableEnding = text.contentOffset;
            NSArray *identifiers = completePayload == website ? @[@"history.result.open", @"history.result.copy", @"history.result.cancel"] : @[@"history.result.copy", @"history.result.cancel"];
            for (NSString *identifier in identifiers) {
                UIButton *button = (UIButton *)[self ownedView:identifier inView:result.view];
                [button layoutIfNeeded];
                CGSize fullTitle = [button.titleLabel sizeThatFits:CGSizeMake(button.titleLabel.bounds.size.width, CGFLOAT_MAX)];
                XCTAssertGreaterThanOrEqual(button.titleLabel.bounds.size.height+0.5, fullTitle.height);
                CGRect rect = [button convertRect:button.bounds toView:actions];
                XCTAssertGreaterThanOrEqual(rect.size.height, 44);
                [self scrollOriginalRectWithOnePixelMargin:rect inScroll:actions];
                XCTAssertTrue(CGRectContainsRect(actions.bounds, rect));
                XCTAssertTrue(CGPointEqualToPoint(text.contentOffset, readableEnding));
            }
            XCTAssertEqualObjects(body.text, completePayload);
        }
    }
}
- (void)testChineseTranslationsCoverEveryResultActionWithoutChangingPayload {
    NSString *path = [NSBundle.mainBundle pathForResource:@"zh-Hans" ofType:@"lproj"];
    XCTAssertNotNil(path); NSBundle *Chinese = [NSBundle bundleWithPath:path];
    NSDictionary *translations = @{@"QR Code": @"二维码", @"Open Website": @"打开网页", @"Copy Result": @"复制内容", @"Cancel": @"取消"};
    for (NSString *key in translations) XCTAssertEqualObjects([Chinese localizedStringForKey:key value:nil table:nil], translations[key]);
}
- (void)testRealUIKitDismissalCopyCancelEscapeAndReopen {
    UIWindow *oldKey = nil; UIWindowScene *scene = nil;
    for (UIScene *candidate in UIApplication.sharedApplication.connectedScenes) if ([candidate isKindOfClass:UIWindowScene.class]) {
        scene = (UIWindowScene *)candidate;
        for (UIWindow *window in scene.windows) if (window.isKeyWindow) oldKey = window;
        if (oldKey) break;
    }
    XCTAssertNotNil(scene); if (!scene) return;
    UIWindow *window = [[UIWindow alloc] initWithWindowScene:scene];
    UIViewController *host = [UIViewController new]; window.rootViewController = host;
    NSArray *oldPasteboard = UIPasteboard.generalPasteboard.items;
    @try {
        [window makeKeyAndVisible];
        for (NSUInteger cycle = 0; cycle < 3; cycle++) {
            NSString *payload = [NSString stringWithFormat:@"Complete result %lu 你好 🌈", (unsigned long)cycle];
            QRPhoneResultViewController *result = [[QRPhoneResultViewController alloc] initWithPayload:payload openWebsiteHandler:^(NSURL *URL) { XCTFail(@"Text cannot open a URL"); }];
            XCTestExpectation *presented = [self expectationWithDescription:@"Native presentation completed"];
            [host presentViewController:result animated:NO completion:^{ [presented fulfill]; }];
            [self waitForExpectations:@[presented] timeout:5];
            XCTAssertEqual(host.presentedViewController, result);
            UIPasteboard.generalPasteboard.string = @"unchanged";
            if (cycle == 0) [result cancel]; else if (cycle == 1) [result copyResult]; else XCTAssertTrue([result accessibilityPerformEscape]);
            NSPredicate *closed = [NSPredicate predicateWithBlock:^BOOL(id object, NSDictionary *bindings) {
                BOOL copied = cycle != 1 || [UIPasteboard.generalPasteboard.string isEqualToString:payload];
                return host.presentedViewController == nil && copied;
            }];
            XCTNSPredicateExpectation *dismissed = [[XCTNSPredicateExpectation alloc] initWithPredicate:closed object:host];
            XCTAssertEqual([XCTWaiter waitForExpectations:@[dismissed] timeout:5], XCTWaiterResultCompleted);
            XCTAssertEqualObjects(UIPasteboard.generalPasteboard.string, cycle == 1 ? payload : @"unchanged");
        }
    } @finally {
        [host dismissViewControllerAnimated:NO completion:nil]; window.hidden = YES;
        [oldKey makeKeyWindow]; UIPasteboard.generalPasteboard.items = oldPasteboard;
    }
}
@end
