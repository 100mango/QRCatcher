#import "QRPhoneResultViewController.h"
#import "QRActionButton.h"
#import "NSString+Tools.h"

@interface QRPhoneResultViewController ()
@property (nonatomic, copy, readwrite) NSString *payload;
@property (nonatomic, copy) void (^openWebsiteHandler)(NSURL *URL);
@property (nonatomic, strong) NSURL *websiteURL;
@property (nonatomic, strong) UILabel *heading;
@property (nonatomic, strong) UIStackView *actions;
@property (nonatomic) BOOL finishing;
@end

@implementation QRPhoneResultViewController
- (instancetype)initWithPayload:(NSString *)payload openWebsiteHandler:(void (^)(NSURL *))openWebsiteHandler {
    if ((self = [super initWithNibName:nil bundle:nil])) {
        _payload = [payload copy];
        _websiteURL = [NSString HTTPURLFromString:_payload];
        _openWebsiteHandler = [openWebsiteHandler copy];
        self.modalPresentationStyle = UIModalPresentationFullScreen;
    }
    return self;
}
- (UIButton *)button:(NSString *)title identifier:(NSString *)identifier action:(SEL)action {
    UIButton *button = [QRActionButton buttonWithType:UIButtonTypeSystem];
    [button setTitle:NSLocalizedString(title, nil) forState:UIControlStateNormal];
    button.titleLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleHeadline];
    button.titleLabel.adjustsFontForContentSizeCategory = YES;
    button.titleLabel.numberOfLines = 0;
    button.titleLabel.adjustsFontSizeToFitWidth = NO;
    button.titleLabel.lineBreakMode = NSLineBreakByWordWrapping;
    button.titleLabel.textAlignment = NSTextAlignmentCenter;
    button.accessibilityIdentifier = identifier;
    [button setContentCompressionResistancePriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisVertical];
    [button addTarget:self action:action forControlEvents:UIControlEventTouchUpInside];
    [button.heightAnchor constraintGreaterThanOrEqualToConstant:44].active = YES;
    return button;
}
- (void)loadView {
    self.view = [UIView new];
    self.view.backgroundColor = UIColor.systemBackgroundColor;
    self.view.accessibilityIdentifier = @"history.result";
    self.view.accessibilityViewIsModal = YES;

    // Own both scroll panes. No UIAlertController descendants are inspected or
    // changed. Long text and large action titles keep their full intrinsic size.
    UIScrollView *textScroll = [UIScrollView new];
    textScroll.accessibilityIdentifier = @"history.result.text-scroll";
    UIScrollView *actionScroll = [UIScrollView new];
    actionScroll.accessibilityIdentifier = @"history.result.action-scroll";
    for (UIScrollView *scroll in @[textScroll, actionScroll]) {
        scroll.translatesAutoresizingMaskIntoConstraints = NO;
        scroll.contentInsetAdjustmentBehavior = UIScrollViewContentInsetAdjustmentNever;
        [self.view addSubview:scroll];
    }
    self.heading = [UILabel new];
    self.heading.text = NSLocalizedString(@"QR Code", nil);
    self.heading.font = [UIFont preferredFontForTextStyle:UIFontTextStyleTitle2];
    self.heading.textColor = UIColor.labelColor;
    self.heading.adjustsFontForContentSizeCategory = YES;
    self.heading.numberOfLines = 0;
    self.heading.accessibilityTraits |= UIAccessibilityTraitHeader;
    self.heading.accessibilityIdentifier = @"history.result.title";
    UILabel *body = [UILabel new];
    body.text = self.payload;
    body.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    body.textColor = UIColor.labelColor;
    body.adjustsFontForContentSizeCategory = YES;
    body.numberOfLines = 0;
    body.lineBreakMode = NSLineBreakByCharWrapping;
    body.accessibilityIdentifier = @"history.result.payload";
    UIStackView *text = [[UIStackView alloc] initWithArrangedSubviews:@[self.heading, body]];
    text.axis = UILayoutConstraintAxisVertical; text.spacing = 16;
    text.translatesAutoresizingMaskIntoConstraints = NO;
    [textScroll addSubview:text];

    NSMutableArray<UIView *> *buttons = [NSMutableArray new];
    if (self.websiteURL) [buttons addObject:[self button:@"Open Website" identifier:@"history.result.open" action:@selector(openWebsite)]];
    [buttons addObject:[self button:@"Copy Result" identifier:@"history.result.copy" action:@selector(copyResult)]];
    [buttons addObject:[self button:@"Cancel" identifier:@"history.result.cancel" action:@selector(cancel)]];
    self.actions = [[UIStackView alloc] initWithArrangedSubviews:buttons];
    self.actions.axis = UILayoutConstraintAxisVertical; self.actions.spacing = 8;
    self.actions.translatesAutoresizingMaskIntoConstraints = NO;
    [actionScroll addSubview:self.actions];

    UILayoutGuide *safe = self.view.safeAreaLayoutGuide;
    NSLayoutConstraint *naturalActions = [actionScroll.heightAnchor constraintEqualToAnchor:self.actions.heightAnchor constant:16];
    naturalActions.priority = UILayoutPriorityDefaultHigh;
    [NSLayoutConstraint activateConstraints:@[
        [textScroll.topAnchor constraintEqualToAnchor:safe.topAnchor],
        [textScroll.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor],
        [textScroll.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor],
        [textScroll.bottomAnchor constraintEqualToAnchor:actionScroll.topAnchor constant:-16],
        [actionScroll.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor],
        [actionScroll.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor],
        [actionScroll.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor constant:-16],
        [actionScroll.heightAnchor constraintLessThanOrEqualToAnchor:safe.heightAnchor multiplier:0.45],
        [actionScroll.heightAnchor constraintGreaterThanOrEqualToConstant:44],
        naturalActions,
        [text.topAnchor constraintEqualToAnchor:textScroll.contentLayoutGuide.topAnchor constant:20],
        [text.bottomAnchor constraintEqualToAnchor:textScroll.contentLayoutGuide.bottomAnchor constant:-20],
        [text.leadingAnchor constraintEqualToAnchor:textScroll.contentLayoutGuide.leadingAnchor constant:20],
        [text.trailingAnchor constraintEqualToAnchor:textScroll.contentLayoutGuide.trailingAnchor constant:-20],
        [text.widthAnchor constraintEqualToAnchor:textScroll.frameLayoutGuide.widthAnchor constant:-40],
        [self.actions.topAnchor constraintEqualToAnchor:actionScroll.contentLayoutGuide.topAnchor constant:8],
        [self.actions.bottomAnchor constraintEqualToAnchor:actionScroll.contentLayoutGuide.bottomAnchor constant:-8],
        [self.actions.leadingAnchor constraintEqualToAnchor:actionScroll.contentLayoutGuide.leadingAnchor constant:20],
        [self.actions.trailingAnchor constraintEqualToAnchor:actionScroll.contentLayoutGuide.trailingAnchor constant:-20],
        [self.actions.widthAnchor constraintEqualToAnchor:actionScroll.frameLayoutGuide.widthAnchor constant:-40]
    ]];
}
- (void)viewDidAppear:(BOOL)animated {
    [super viewDidAppear:animated];
    UIAccessibilityPostNotification(UIAccessibilityScreenChangedNotification, self.heading);
}
- (void)finishWithAction:(nullable void (^)(void))action {
    if (self.finishing) return;
    self.finishing = YES;
    for (UIButton *button in self.actions.arrangedSubviews) button.enabled = NO;
    // UIKit's real dismissal owns the transition. Side effects run only after
    // dismissal, and rapid repeated taps cannot open/copy/dismiss twice.
    [self dismissViewControllerAnimated:YES completion:action];
}
- (void)copyResult {
    NSString *payload = self.payload;
    [self finishWithAction:^{ UIPasteboard.generalPasteboard.string = payload; }];
}
- (void)openWebsite {
    if (!self.websiteURL) return;
    NSURL *URL = self.websiteURL;
    void (^open)(NSURL *) = self.openWebsiteHandler;
    [self finishWithAction:^{ open(URL); }];
}
- (void)cancel { [self finishWithAction:nil]; }
- (BOOL)accessibilityPerformEscape { [self cancel]; return YES; }
@end
