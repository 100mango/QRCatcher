#import "QRPrivacyViewController.h"
#import "QRActionButton.h"

#if DEBUG
#include <math.h>
static BOOL QRPrivacySystemEnabled;
static BOOL QRPrivacySystemUnknown;
static NSUInteger QRPrivacySystemRequests;
static NSUInteger QRPrivacySystemCompletions;
static BOOL QRPrivacySystemOpened;
static double QRPrivacySystemStarted;
static double QRPrivacySystemCompleted;
static NSString *QRPrivacySystemRequestID;
static NSString *QRPrivacySystemLaunchID;
static NSString *QRPrivacySystemURL;
static __weak UILabel *QRPrivacySystemLabel;
static NSString *QRPrivacySystemCameraValue;

int QRPrivacySystemOpenObservationQualifies(unsigned long requests, unsigned long completions,
                                            int opened, int unknown, double started, double completed) {
    double elapsed = completed - started;
    return requests == 1 && completions == 1 && opened && !unknown &&
        isfinite(started) && isfinite(completed) && isfinite(elapsed) && elapsed >= 0 && elapsed < 10;
}
BOOL QRPrivacySystemOpenObservationLaunchGate(NSArray<NSString *> *arguments, int appPID) {
    if ([arguments containsObject:@"-photo-import-observation-v1"]) return NO;
    NSUInteger uiCount = 0, tokenCount = 0, requestCount = 0;
    for (NSString *argument in arguments) {
        if ([argument isEqualToString:@"-ui-testing"]) uiCount += 1;
        if ([argument isEqualToString:@"-privacy-system-open-v1"]) tokenCount += 1;
        if ([argument isEqualToString:@"-privacy-system-open-request-id"]) requestCount += 1;
    }
    if (uiCount != 1 || tokenCount != 1 || requestCount != 1 || appPID <= 0) return NO;
    NSUInteger index = [arguments indexOfObject:@"-privacy-system-open-request-id"];
    if (index + 1 >= arguments.count) return NO;
    NSString *requestID = arguments[index + 1];
    NSUUID *request = [[NSUUID alloc] initWithUUIDString:requestID];
    return request && [request.UUIDString isEqualToString:requestID];
}
static NSString *QRPrivacySystemEncodedValue(void) {
    if (!QRPrivacySystemEnabled) return QRPrivacySystemCameraValue;
    BOOL accepted = QRPrivacySystemOpenObservationQualifies(QRPrivacySystemRequests, QRPrivacySystemCompletions,
        QRPrivacySystemOpened, QRPrivacySystemUnknown, QRPrivacySystemStarted, QRPrivacySystemCompleted);
    NSString *status = accepted ? @"system_accepted" :
        (!QRPrivacySystemUnknown && QRPrivacySystemRequests == 0 && QRPrivacySystemCompletions == 0 ? @"baseline" : @"UNKNOWN");
    NSDictionary *record = @{@"version": @1, @"case": @"testDeniedCameraAndEmptyHistory",
        @"request_id": QRPrivacySystemRequestID, @"launch_id": QRPrivacySystemLaunchID,
        @"app_pid": @(NSProcessInfo.processInfo.processIdentifier), @"requests": @(QRPrivacySystemRequests),
        @"completions": @(QRPrivacySystemCompletions),
        @"opened": QRPrivacySystemCompletions ? (id)[NSNumber numberWithBool:QRPrivacySystemOpened] : NSNull.null,
        @"url": QRPrivacySystemURL ?: (id)NSNull.null,
        @"request_uptime": QRPrivacySystemRequests && isfinite(QRPrivacySystemStarted) ? (id)@(QRPrivacySystemStarted) : NSNull.null,
        @"completion_uptime": QRPrivacySystemCompletions && isfinite(QRPrivacySystemCompleted) ? (id)@(QRPrivacySystemCompleted) : NSNull.null,
        @"status": status, @"page_rendered": @"UNKNOWN"};
    NSData *data = [NSJSONSerialization dataWithJSONObject:record options:NSJSONWritingSortedKeys error:nil];
    if (!data || data.length > 1024) { QRPrivacySystemUnknown = YES; return QRPrivacySystemCameraValue; }
    NSString *JSON = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
    return [NSString stringWithFormat:@"%@ privacy_system_open_v1=%@", QRPrivacySystemCameraValue ?: @"", JSON];
}
static void QRPrivacySystemPublish(void) {
    if (QRPrivacySystemEnabled && QRPrivacySystemLabel) QRPrivacySystemLabel.accessibilityValue = QRPrivacySystemEncodedValue();
}
void QRPrivacySystemOpenObservationAttach(UILabel *label) {
    if (!QRPrivacySystemEnabled) {
        NSArray *arguments = NSProcessInfo.processInfo.arguments;
        if (!QRPrivacySystemOpenObservationLaunchGate(arguments, NSProcessInfo.processInfo.processIdentifier)) return;
        QRPrivacySystemRequestID = arguments[[arguments indexOfObject:@"-privacy-system-open-request-id"] + 1];
        QRPrivacySystemLaunchID = NSUUID.UUID.UUIDString;
        QRPrivacySystemEnabled = YES;
    }
    QRPrivacySystemLabel = label;
    QRPrivacySystemCameraValue = label.accessibilityValue;
    QRPrivacySystemPublish();
}
NSString *QRPrivacySystemOpenObservationMergeCameraValue(NSString *cameraValue) {
    if (!QRPrivacySystemEnabled) return cameraValue;
    QRPrivacySystemCameraValue = cameraValue;
    return QRPrivacySystemEncodedValue();
}
static void QRPrivacySystemRecordRequest(NSURL *URL) {
    QRPrivacySystemRequests = MIN(QRPrivacySystemRequests + 1, 2);
    if (QRPrivacySystemRequests != 1 || QRPrivacySystemCompletions != 0 || !NSThread.isMainThread) QRPrivacySystemUnknown = YES;
    QRPrivacySystemURL = URL.absoluteString;
    QRPrivacySystemStarted = NSProcessInfo.processInfo.systemUptime;
    QRPrivacySystemPublish();
}
static void QRPrivacySystemRecordCompletion(BOOL opened, BOOL closed) {
    QRPrivacySystemCompletions = MIN(QRPrivacySystemCompletions + 1, 2);
    QRPrivacySystemOpened = opened;
    QRPrivacySystemCompleted = NSProcessInfo.processInfo.systemUptime;
    if (closed || !NSThread.isMainThread || !QRPrivacySystemOpenObservationQualifies(QRPrivacySystemRequests,
        QRPrivacySystemCompletions, opened, QRPrivacySystemUnknown, QRPrivacySystemStarted, QRPrivacySystemCompleted)) QRPrivacySystemUnknown = YES;
    QRPrivacySystemPublish();
}
#endif

@interface QRPrivacyViewController ()
@property (nonatomic, strong) UIButton *externalButton;
@property (nonatomic, strong) UILabel *errorMessage;
@property (nonatomic) BOOL closing;
@property (nonatomic) BOOL opening;
@end

@implementation QRPrivacyViewController
- (UILabel *)label:(NSString *)text identifier:(NSString *)identifier style:(UIFontTextStyle)style {
    UILabel *label = [UILabel new];
    label.text = NSLocalizedString(text, nil);
    label.numberOfLines = 0;
    label.lineBreakMode = NSLineBreakByWordWrapping;
    label.font = [UIFont preferredFontForTextStyle:style];
    label.adjustsFontForContentSizeCategory = YES;
    label.textColor = UIColor.labelColor;
    label.accessibilityIdentifier = identifier;
    return label;
}
- (void)viewDidLoad {
    [super viewDidLoad];
    self.title = NSLocalizedString(@"Privacy Policy", nil);
    self.view.backgroundColor = UIColor.systemBackgroundColor;
    self.view.accessibilityViewIsModal = YES;
    self.navigationItem.leftBarButtonItem = [[UIBarButtonItem alloc] initWithTitle:NSLocalizedString(@"Close", nil) style:UIBarButtonItemStyleDone target:self action:@selector(close)];
    self.navigationItem.leftBarButtonItem.accessibilityIdentifier = @"privacy.close";

    // Keep the approved policy wording local. Opening this controller does not
    // construct a WebView, request a document, or fall back to an online page.
    UILabel *body = [self label:@"Celluloid, QRCatcher, and TouchColor process photos, camera images, QR codes, or color data locally on your device. The developer does not collect or upload this data. Actions you choose to take, such as sharing or opening links, and system services such as iCloud sync are handled by the respective services. For privacy questions, contact 100mango@gmail.com. Local data can be deleted through the relevant app or system, and permissions can be revoked in system settings." identifier:@"privacy.body" style:UIFontTextStyleBody];
    UILabel *services = [self label:@"System backups, file providers, the clipboard, and services you choose may handle data according to your settings." identifier:@"privacy.systemServices" style:UIFontTextStyleBody];
    UILabel *website = [self label:@"GitHub Pages records visitor IP addresses for security." identifier:@"privacy.websiteNotice" style:UIFontTextStyleFootnote];
    [website setContentCompressionResistancePriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisVertical];
    self.errorMessage = [self label:@"This website could not be opened." identifier:@"privacy.error" style:UIFontTextStyleBody];
    self.errorMessage.hidden = YES;
    UIStackView *text = [[UIStackView alloc] initWithArrangedSubviews:@[body, services, self.errorMessage]];
    text.axis = UILayoutConstraintAxisVertical;
    text.spacing = 16;
    text.translatesAutoresizingMaskIntoConstraints = NO;
    UIScrollView *content = [UIScrollView new];
    content.accessibilityIdentifier = @"privacy.content";
    content.translatesAutoresizingMaskIntoConstraints = NO;
    content.contentInsetAdjustmentBehavior = UIScrollViewContentInsetAdjustmentNever;
    [self.view addSubview:content];
    [content addSubview:text];

    self.externalButton = [QRActionButton buttonWithType:UIButtonTypeSystem];
    [self.externalButton setTitle:NSLocalizedString(@"Open in Browser", nil) forState:UIControlStateNormal];
    self.externalButton.titleLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleHeadline];
    self.externalButton.titleLabel.adjustsFontForContentSizeCategory = YES;
    self.externalButton.titleLabel.numberOfLines = 0;
    self.externalButton.titleLabel.adjustsFontSizeToFitWidth = NO;
    self.externalButton.titleLabel.lineBreakMode = NSLineBreakByWordWrapping;
    self.externalButton.titleLabel.textAlignment = NSTextAlignmentCenter;
    self.externalButton.accessibilityIdentifier = @"privacy.externalPolicy";
    [self.externalButton setContentCompressionResistancePriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisVertical];
    [self.externalButton addTarget:self action:@selector(openPolicyInBrowser) forControlEvents:UIControlEventTouchUpInside];
    [self.externalButton.heightAnchor constraintGreaterThanOrEqualToConstant:44].active = YES;
    UIStackView *actions = [[UIStackView alloc] initWithArrangedSubviews:@[website, self.externalButton]];
    actions.axis = UILayoutConstraintAxisVertical;
    actions.spacing = 8;
    actions.translatesAutoresizingMaskIntoConstraints = NO;
    UIScrollView *actionScroll = [UIScrollView new];
    actionScroll.accessibilityIdentifier = @"privacy.actionScroll";
    actionScroll.translatesAutoresizingMaskIntoConstraints = NO;
    actionScroll.contentInsetAdjustmentBehavior = UIScrollViewContentInsetAdjustmentNever;
    [self.view addSubview:actionScroll];
    [actionScroll addSubview:actions];
    UILayoutGuide *safe = self.view.safeAreaLayoutGuide;
    NSLayoutConstraint *naturalActions = [actionScroll.heightAnchor constraintEqualToAnchor:actions.heightAnchor constant:16];
    naturalActions.priority = UILayoutPriorityDefaultHigh;
    [NSLayoutConstraint activateConstraints:@[
        [content.topAnchor constraintEqualToAnchor:safe.topAnchor],
        [content.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor],
        [content.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor],
        [content.bottomAnchor constraintEqualToAnchor:actionScroll.topAnchor constant:-16],
        [actionScroll.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor],
        [actionScroll.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor],
        [actionScroll.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor constant:-16],
        [actionScroll.heightAnchor constraintGreaterThanOrEqualToConstant:44],
        [actionScroll.heightAnchor constraintLessThanOrEqualToAnchor:safe.heightAnchor multiplier:0.45],
        naturalActions,
        [text.topAnchor constraintEqualToAnchor:content.contentLayoutGuide.topAnchor constant:24],
        [text.bottomAnchor constraintEqualToAnchor:content.contentLayoutGuide.bottomAnchor constant:-24],
        [text.leadingAnchor constraintEqualToAnchor:content.contentLayoutGuide.leadingAnchor constant:24],
        [text.trailingAnchor constraintEqualToAnchor:content.contentLayoutGuide.trailingAnchor constant:-24],
        [text.widthAnchor constraintEqualToAnchor:content.frameLayoutGuide.widthAnchor constant:-48],
        [actions.topAnchor constraintEqualToAnchor:actionScroll.contentLayoutGuide.topAnchor constant:8],
        [actions.bottomAnchor constraintEqualToAnchor:actionScroll.contentLayoutGuide.bottomAnchor constant:-8],
        [actions.leadingAnchor constraintEqualToAnchor:actionScroll.contentLayoutGuide.leadingAnchor constant:24],
        [actions.trailingAnchor constraintEqualToAnchor:actionScroll.contentLayoutGuide.trailingAnchor constant:-24],
        [actions.widthAnchor constraintEqualToAnchor:actionScroll.frameLayoutGuide.widthAnchor constant:-48]
    ]];
}
- (void)openExternalURL:(NSURL *)URL completion:(void (^)(BOOL))completion {
#if DEBUG
    if (QRPrivacySystemEnabled) {
        void (^originalCompletion)(BOOL) = completion;
        __weak typeof(self) weakSelf = self;
        completion = ^(BOOL opened) {
            QRPrivacyViewController *controller = weakSelf;
            QRPrivacySystemRecordCompletion(opened, !controller || controller.closing);
            if (originalCompletion) originalCompletion(opened);
        };
        // Only this actual public API boundary records a request. A host spy
        // overriding openExternalURL:completion: cannot create system evidence.
        QRPrivacySystemRecordRequest(URL);
    }
#endif
    [UIApplication.sharedApplication openURL:URL options:@{} completionHandler:completion];
}
- (void)openPolicyInBrowser {
    if (self.closing || self.opening) return;
    self.opening = YES;
    self.externalButton.enabled = NO;
    self.errorMessage.hidden = YES;
    NSURL *URL = [NSURL URLWithString:@"https://100mango.github.io/app-privacy/"];
    __weak typeof(self) weakSelf = self;
    [self openExternalURL:URL completion:^(BOOL opened) {
        QRPrivacyViewController *strongSelf = weakSelf;
        if (!strongSelf || strongSelf.closing) return;
        strongSelf.opening = NO;
        strongSelf.externalButton.enabled = YES;
        strongSelf.errorMessage.hidden = opened;
    }];
}
- (void)close {
    if (self.closing) return;
    self.closing = YES;
    void (^cleanup)(void) = self.dismissalHandler;
    if (cleanup) cleanup();
    UIViewController *presentation = self.navigationController ?: self;
    if (presentation.presentingViewController && !presentation.isBeingDismissed) {
        [presentation dismissViewControllerAnimated:YES completion:cleanup];
    } else if (presentation.transitionCoordinator) {
        [presentation.transitionCoordinator animateAlongsideTransition:nil completion:^(id<UIViewControllerTransitionCoordinatorContext> context) { if (cleanup) cleanup(); }];
    }
}
@end
