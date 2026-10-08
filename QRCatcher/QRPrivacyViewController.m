#import "QRPrivacyViewController.h"
#import <WebKit/WebKit.h>
@interface QRPrivacyViewController () <WKNavigationDelegate>
@property (nonatomic, strong) WKWebView *webView;
@property (nonatomic, strong) UIStackView *errorView;
@property (nonatomic, strong) UIScrollView *errorScroll;
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
    message.accessibilityIdentifier = @"privacy.error";
    message.numberOfLines = 0;
    message.textAlignment = NSTextAlignmentCenter;
    message.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    message.adjustsFontForContentSizeCategory = YES;
    UIButton *retry = [UIButton buttonWithType:UIButtonTypeSystem];
    [retry setTitle:NSLocalizedString(@"Retry", nil) forState:UIControlStateNormal];
    retry.accessibilityIdentifier = @"privacy.retry";
    retry.titleLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleHeadline];
    retry.titleLabel.adjustsFontForContentSizeCategory = YES;
    retry.titleLabel.numberOfLines = 0;
    [retry addTarget:self action:@selector(loadPolicy) forControlEvents:UIControlEventTouchUpInside];
    [retry.heightAnchor constraintGreaterThanOrEqualToConstant:44].active = YES;
    self.errorView = [[UIStackView alloc] initWithArrangedSubviews:@[message, retry]];
    self.errorView.axis = UILayoutConstraintAxisVertical;
    self.errorView.spacing = 16;
    self.errorView.translatesAutoresizingMaskIntoConstraints = NO;
    self.errorView.hidden = YES;
    self.errorScroll = [UIScrollView new];
    self.errorScroll.translatesAutoresizingMaskIntoConstraints = NO;
    self.errorScroll.hidden = YES;
    [self.view addSubview:self.errorScroll];
    [self.errorScroll addSubview:self.errorView];
    UILayoutGuide *safe = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [self.webView.topAnchor constraintEqualToAnchor:safe.topAnchor],
        [self.webView.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor],
        [self.webView.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor],
        [self.webView.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor],
        [self.activity.centerXAnchor constraintEqualToAnchor:safe.centerXAnchor],
        [self.activity.centerYAnchor constraintEqualToAnchor:safe.centerYAnchor],
        [self.errorScroll.topAnchor constraintEqualToAnchor:safe.topAnchor],
        [self.errorScroll.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor],
        [self.errorScroll.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor],
        [self.errorScroll.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor],
        [self.errorView.topAnchor constraintEqualToAnchor:self.errorScroll.contentLayoutGuide.topAnchor constant:24],
        [self.errorView.bottomAnchor constraintEqualToAnchor:self.errorScroll.contentLayoutGuide.bottomAnchor constant:-24],
        [self.errorView.leadingAnchor constraintEqualToAnchor:self.errorScroll.contentLayoutGuide.leadingAnchor constant:24],
        [self.errorView.trailingAnchor constraintEqualToAnchor:self.errorScroll.contentLayoutGuide.trailingAnchor constant:-24],
        [self.errorView.widthAnchor constraintEqualToAnchor:self.errorScroll.frameLayoutGuide.widthAnchor constant:-48]
    ]];
    [self loadPolicy];
}
- (void)loadPolicy {
    if (self.closing) return;
    self.errorView.hidden = YES;
    self.errorScroll.hidden = YES;
    self.webView.hidden = NO;
    [self.activity startAnimating];
    NSURL *URL = [NSURL URLWithString:@"https://100mango.github.io/app-privacy/"];
    [self.webView loadRequest:[NSURLRequest requestWithURL:URL cachePolicy:NSURLRequestReloadIgnoringLocalCacheData timeoutInterval:20]];
}
- (void)webView:(WKWebView *)webView didFinishNavigation:(WKNavigation *)navigation {
    [self.activity stopAnimating];
}
- (void)showLoadError:(NSError *)error {
    if (self.closing || ([error.domain isEqualToString:NSURLErrorDomain] && error.code == NSURLErrorCancelled)) return;
    [self.activity stopAnimating];
    self.errorView.hidden = NO;
    self.errorScroll.hidden = NO;
    self.webView.hidden = YES;
}
- (void)webView:(WKWebView *)webView didFailProvisionalNavigation:(WKNavigation *)navigation withError:(NSError *)error { [self showLoadError:error]; }
- (void)webView:(WKWebView *)webView didFailNavigation:(WKNavigation *)navigation withError:(NSError *)error { [self showLoadError:error]; }
- (void)webViewWebContentProcessDidTerminate:(WKWebView *)webView {
    [self showLoadError:[NSError errorWithDomain:NSURLErrorDomain code:NSURLErrorUnknown userInfo:nil]];
}
- (BOOL)isApprovedDocumentURL:(NSURL *)URL {
    NSURLComponents *parts = [NSURLComponents componentsWithURL:URL resolvingAgainstBaseURL:NO];
    return [parts.scheme.lowercaseString isEqualToString:@"https"] &&
        [parts.host.lowercaseString isEqualToString:@"100mango.github.io"] &&
        [parts.path isEqualToString:@"/app-privacy/"] && !parts.query.length && !parts.user.length && !parts.password.length &&
        (!parts.port || parts.port.integerValue == 443);
}
- (void)webView:(WKWebView *)webView decidePolicyForNavigationResponse:(WKNavigationResponse *)response decisionHandler:(void (^)(WKNavigationResponsePolicy))decisionHandler {
    NSHTTPURLResponse *HTTP = [response.response isKindOfClass:NSHTTPURLResponse.class] ? (NSHTTPURLResponse *)response.response : nil;
    BOOL allowed = [self isApprovedDocumentURL:response.response.URL] && response.canShowMIMEType &&
        [response.response.MIMEType.lowercaseString isEqualToString:@"text/html"] && HTTP.statusCode >= 200 && HTTP.statusCode < 300;
    if (!allowed && response.forMainFrame) {
        [self showLoadError:[NSError errorWithDomain:NSURLErrorDomain code:NSURLErrorBadServerResponse userInfo:nil]];
    }
    decisionHandler(allowed ? WKNavigationResponsePolicyAllow : WKNavigationResponsePolicyCancel);
}
- (void)webView:(WKWebView *)webView decidePolicyForNavigationAction:(WKNavigationAction *)action decisionHandler:(void (^)(WKNavigationActionPolicy))decisionHandler {
    NSURLComponents *parts = [NSURLComponents componentsWithURL:action.request.URL resolvingAgainstBaseURL:NO];
    BOOL approvedContact = [parts.scheme.lowercaseString isEqualToString:@"mailto"] &&
        [parts.path.lowercaseString isEqualToString:@"100mango@gmail.com"] && !parts.query.length && !parts.fragment.length &&
        !parts.host.length && !parts.user.length && !parts.password.length && !parts.port;
    if (approvedContact && action.navigationType == WKNavigationTypeLinkActivated) {
        [UIApplication.sharedApplication openURL:action.request.URL options:@{} completionHandler:nil];
    }
    BOOL approvedDocument = [self isApprovedDocumentURL:action.request.URL];
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
