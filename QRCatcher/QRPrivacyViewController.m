#import "QRPrivacyViewController.h"
#import <WebKit/WebKit.h>
@interface QRPrivacyViewController () <WKNavigationDelegate>
@property (nonatomic, strong) WKWebView *webView;
@property (nonatomic, strong) UIStackView *errorView;
@property (nonatomic, strong) UIActivityIndicatorView *activity;
@property (nonatomic) BOOL closing;
@end
@implementation QRPrivacyViewController
- (void)viewDidLoad {
    [super viewDidLoad];
    self.title = NSLocalizedString(@"Privacy Policy", nil);
    self.view.backgroundColor = UIColor.systemBackgroundColor;
    self.navigationItem.leftBarButtonItem = [[UIBarButtonItem alloc] initWithTitle:NSLocalizedString(@"Close", nil) style:UIBarButtonItemStyleDone target:self action:@selector(close)];
    self.navigationItem.leftBarButtonItem.accessibilityIdentifier = @"privacy.close";
    WKWebViewConfiguration *configuration = [WKWebViewConfiguration new];
    configuration.websiteDataStore = WKWebsiteDataStore.nonPersistentDataStore;
    configuration.defaultWebpagePreferences.allowsContentJavaScript = NO;
    self.webView = [[WKWebView alloc] initWithFrame:CGRectZero configuration:configuration];
    self.webView.navigationDelegate = self;
    self.webView.accessibilityIdentifier = @"privacy.content";
    self.webView.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.webView];
    self.activity = [[UIActivityIndicatorView alloc] initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleMedium];
    self.activity.hidesWhenStopped = YES;
    self.activity.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.activity];
    UILabel *message = [UILabel new];
    message.text = NSLocalizedString(@"The privacy policy could not load. Check your connection and try again.", nil);
    message.numberOfLines = 0;
    message.textAlignment = NSTextAlignmentCenter;
    message.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    message.adjustsFontForContentSizeCategory = YES;
    UIButton *retry = [UIButton buttonWithType:UIButtonTypeSystem];
    [retry setTitle:NSLocalizedString(@"Retry", nil) forState:UIControlStateNormal];
    retry.accessibilityIdentifier = @"privacy.retry";
    [retry addTarget:self action:@selector(loadPolicy) forControlEvents:UIControlEventTouchUpInside];
    [retry.heightAnchor constraintGreaterThanOrEqualToConstant:44].active = YES;
    self.errorView = [[UIStackView alloc] initWithArrangedSubviews:@[message, retry]];
    self.errorView.axis = UILayoutConstraintAxisVertical;
    self.errorView.spacing = 16;
    self.errorView.translatesAutoresizingMaskIntoConstraints = NO;
    self.errorView.hidden = YES;
    [self.view addSubview:self.errorView];
    UILayoutGuide *safe = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [self.webView.topAnchor constraintEqualToAnchor:safe.topAnchor],
        [self.webView.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor],
        [self.webView.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor],
        [self.webView.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor],
        [self.activity.centerXAnchor constraintEqualToAnchor:safe.centerXAnchor],
        [self.activity.centerYAnchor constraintEqualToAnchor:safe.centerYAnchor],
        [self.errorView.centerYAnchor constraintEqualToAnchor:safe.centerYAnchor],
        [self.errorView.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:24],
        [self.errorView.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-24]
    ]];
    [self loadPolicy];
}
- (void)loadPolicy {
    self.errorView.hidden = YES;
    self.webView.hidden = NO;
    [self.activity startAnimating];
    NSURL *URL = [NSURL URLWithString:@"https://100mango.github.io/app-privacy/"];
    [self.webView loadRequest:[NSURLRequest requestWithURL:URL cachePolicy:NSURLRequestReloadIgnoringLocalCacheData timeoutInterval:20]];
}
- (void)webView:(WKWebView *)webView didFinishNavigation:(WKNavigation *)navigation {
    [self.activity stopAnimating];
}
- (void)showLoadError:(NSError *)error {
    if (error.code == NSURLErrorCancelled) return;
    [self.activity stopAnimating];
    self.errorView.hidden = NO;
    self.webView.hidden = YES;
}
- (void)webView:(WKWebView *)webView didFailProvisionalNavigation:(WKNavigation *)navigation withError:(NSError *)error { [self showLoadError:error]; }
- (void)webView:(WKWebView *)webView didFailNavigation:(WKNavigation *)navigation withError:(NSError *)error { [self showLoadError:error]; }
- (void)webView:(WKWebView *)webView decidePolicyForNavigationAction:(WKNavigationAction *)action decisionHandler:(void (^)(WKNavigationActionPolicy))decisionHandler {
    NSURLComponents *parts = [NSURLComponents componentsWithURL:action.request.URL resolvingAgainstBaseURL:NO];
    BOOL approvedContact = [parts.scheme.lowercaseString isEqualToString:@"mailto"] &&
        [parts.path.lowercaseString isEqualToString:@"100mango@gmail.com"] && !parts.query.length && !parts.fragment.length;
    if (approvedContact && action.navigationType == WKNavigationTypeLinkActivated) {
        [UIApplication.sharedApplication openURL:action.request.URL options:@{} completionHandler:nil];
    }
    BOOL approvedDocument = [parts.scheme.lowercaseString isEqualToString:@"https"] &&
        [parts.host.lowercaseString isEqualToString:@"100mango.github.io"] &&
        [parts.path isEqualToString:@"/app-privacy/"] && !parts.query.length && !parts.user.length && !parts.password.length &&
        (!parts.port || parts.port.integerValue == 443);
    decisionHandler(approvedDocument ? WKNavigationActionPolicyAllow : WKNavigationActionPolicyCancel);
}
- (void)close {
    if (self.closing) return;
    self.closing = YES;
    [self.webView stopLoading];
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
