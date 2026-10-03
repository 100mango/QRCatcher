#import "QRCatchViewController.h"
#import "AppDelegate.h"
#import "NSString+Tools.h"
#import "QRCodeCodec.h"
#import <AVFoundation/AVFoundation.h>
#import <QuartzCore/QuartzCore.h>

@interface QRCatchViewController () <AVCaptureMetadataOutputObjectsDelegate>
@property (nonatomic, strong) UIView *preview;
@property (nonatomic, strong) UIImageView *catcherIndicator;
@property (nonatomic, strong) UILabel *statusLabel;
@property (nonatomic, strong) UILabel *resultLabel;
@property (nonatomic, strong) UIButton *settingsButton;
@property (nonatomic, strong) UIButton *openButton;
@property (nonatomic, strong) UIButton *againButton;
@property (nonatomic, strong) UIButton *resultCopyButton;
@property (nonatomic, strong) CAShapeLayer *ripple;
@property (nonatomic, strong) AVCaptureSession *session;
@property (nonatomic, strong) AVCaptureVideoPreviewLayer *previewLayer;
@property (nonatomic, strong) dispatch_queue_t sessionQueue;
@property (atomic) BOOL visible;
@property (atomic) BOOL ready;
@property (atomic) BOOL wantsCamera;
@property (nonatomic) BOOL hasResult;
@property (nonatomic) BOOL appliedFixture;
@property (nonatomic, copy) NSString *payload;
@end

@implementation QRCatchViewController
- (UIButton *)button:(NSString *)title identifier:(NSString *)identifier action:(SEL)action {
    UIButton *button = [UIButton buttonWithType:UIButtonTypeSystem];
    [button setTitle:NSLocalizedString(title, nil) forState:UIControlStateNormal];
    button.titleLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleHeadline];
    button.titleLabel.adjustsFontForContentSizeCategory = YES;
    button.titleLabel.numberOfLines = 0;
    button.accessibilityIdentifier = identifier;
    [button addTarget:self action:action forControlEvents:UIControlEventTouchUpInside];
    [button.heightAnchor constraintGreaterThanOrEqualToConstant:44].active = YES;
    return button;
}
- (void)loadView {
    self.view = [UIView new];
    self.view.backgroundColor = UIColor.systemBackgroundColor;
    UIScrollView *scroll = [UIScrollView new];
    scroll.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:scroll];
    self.preview = [UIView new];
    self.preview.backgroundColor = UIColor.blackColor;
    self.preview.clipsToBounds = YES;
    self.preview.layer.cornerRadius = 20;
    self.preview.accessibilityIdentifier = @"scan.preview";
    self.catcherIndicator = [[UIImageView alloc] initWithImage:[UIImage imageNamed:@"catcher6_0000_scanning2x"]];
    self.catcherIndicator.contentMode = UIViewContentModeScaleAspectFit;
    self.catcherIndicator.translatesAutoresizingMaskIntoConstraints = NO;
    self.catcherIndicator.isAccessibilityElement = NO;
    [self.preview addSubview:self.catcherIndicator];
    self.statusLabel = [UILabel new];
    self.statusLabel.text = NSLocalizedString(@"Point the camera at a QR code", nil);
    self.statusLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    self.statusLabel.adjustsFontForContentSizeCategory = YES;
    self.statusLabel.numberOfLines = 0;
    self.statusLabel.textAlignment = NSTextAlignmentCenter;
    self.statusLabel.accessibilityIdentifier = @"scan.status";
    self.resultLabel = [UILabel new];
    self.resultLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    self.resultLabel.adjustsFontForContentSizeCategory = YES;
    self.resultLabel.numberOfLines = 0;
    self.resultLabel.lineBreakMode = NSLineBreakByCharWrapping;
    self.resultLabel.accessibilityIdentifier = @"scan.result";
    self.resultLabel.hidden = YES;
    self.settingsButton = [self button:@"Open Settings" identifier:@"scan.settings" action:@selector(openSettings)];
    self.openButton = [self button:@"Open Website" identifier:@"scan.open" action:@selector(openWebsite)];
    self.resultCopyButton = [self button:@"Copy Result" identifier:@"scan.copy" action:@selector(copyResult)];
    self.againButton = [self button:@"Scan Again" identifier:@"scan.again" action:@selector(scanAgain)];
    self.settingsButton.hidden = self.openButton.hidden = self.againButton.hidden = self.resultCopyButton.hidden = YES;
    UIStackView *stack = [[UIStackView alloc] initWithArrangedSubviews:@[self.preview, self.statusLabel, self.resultLabel, self.settingsButton, self.openButton, self.resultCopyButton, self.againButton]];
    stack.axis = UILayoutConstraintAxisVertical;
    stack.spacing = 16;
    stack.translatesAutoresizingMaskIntoConstraints = NO;
    [scroll addSubview:stack];
    UILayoutGuide *safe = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [scroll.topAnchor constraintEqualToAnchor:safe.topAnchor], [scroll.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor],
        [scroll.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor], [scroll.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor],
        [stack.topAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.topAnchor constant:16],
        [stack.bottomAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.bottomAnchor constant:-24],
        [stack.leadingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.leadingAnchor constant:16],
        [stack.trailingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.trailingAnchor constant:-16],
        [stack.widthAnchor constraintEqualToAnchor:scroll.frameLayoutGuide.widthAnchor constant:-32],
        [self.preview.heightAnchor constraintEqualToAnchor:self.preview.widthAnchor multiplier:0.7],
        [self.catcherIndicator.topAnchor constraintEqualToAnchor:self.preview.topAnchor],
        [self.catcherIndicator.bottomAnchor constraintEqualToAnchor:self.preview.bottomAnchor],
        [self.catcherIndicator.leadingAnchor constraintEqualToAnchor:self.preview.leadingAnchor],
        [self.catcherIndicator.trailingAnchor constraintEqualToAnchor:self.preview.trailingAnchor]
    ]];
}
- (void)viewDidLoad {
    [super viewDidLoad];
    self.title = @"QRCatcher";
    self.sessionQueue = dispatch_queue_create("com.100mango.QRCatcher.camera", DISPATCH_QUEUE_SERIAL);
    self.session = [AVCaptureSession new];
    NSNotificationCenter *center = NSNotificationCenter.defaultCenter;
    [center addObserver:self selector:@selector(resumeCamera) name:UIApplicationDidBecomeActiveNotification object:nil];
    [center addObserver:self selector:@selector(pauseCamera) name:UIApplicationWillResignActiveNotification object:nil];
    [center addObserver:self selector:@selector(resumeCamera) name:UISceneDidActivateNotification object:nil];
    [center addObserver:self selector:@selector(pauseCamera) name:UISceneWillDeactivateNotification object:nil];
    [center addObserver:self selector:@selector(captureInterrupted:) name:AVCaptureSessionWasInterruptedNotification object:self.session];
    [center addObserver:self selector:@selector(resumeCamera) name:AVCaptureSessionInterruptionEndedNotification object:self.session];
    [center addObserver:self selector:@selector(captureFailed:) name:AVCaptureSessionRuntimeErrorNotification object:self.session];
    [center addObserver:self selector:@selector(updateRipple) name:UIAccessibilityReduceMotionStatusDidChangeNotification object:nil];
    [self updateRipple];
}
- (void)viewDidAppear:(BOOL)animated {
    [super viewDidAppear:animated];
    self.visible = YES;
#if DEBUG
    NSArray *args = NSProcessInfo.processInfo.arguments;
    if ([args containsObject:@"-ui-testing"] && [args containsObject:@"-fixture-empty"] && !self.appliedFixture) {
        self.appliedFixture = YES;
        [self handlePayload:nil];
        return;
    }
    NSUInteger index = [args indexOfObject:@"-fixture-payload"];
    if ([args containsObject:@"-ui-testing"] && !self.appliedFixture && index != NSNotFound && index + 1 < args.count) {
        self.appliedFixture = YES;
        UIImage *QR = [QRCodeCodec imageForPayload:args[index + 1]];
        NSString *decoded = [[QRCodeCodec payloadsInImage:QR] firstObject];
        [self handlePayload:decoded];
        return;
    }
#endif
    [self resumeCamera];
}
- (void)viewWillDisappear:(BOOL)animated {
    [super viewWillDisappear:animated];
    self.visible = NO;
    [self pauseCamera];
}
- (void)dealloc { [NSNotificationCenter.defaultCenter removeObserver:self]; }
- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];
    self.previewLayer.frame = self.preview.bounds;
    self.ripple.position = CGPointMake(CGRectGetMidX(self.preview.bounds), CGRectGetMidY(self.preview.bounds));
}
- (void)updateRipple {
    [self.ripple removeFromSuperlayer];
    if (UIAccessibilityIsReduceMotionEnabled() || self.hasResult) return;
    self.ripple = [CAShapeLayer layer];
    self.ripple.path = [UIBezierPath bezierPathWithOvalInRect:CGRectMake(-2, -2, 4, 4)].CGPath;
    self.ripple.strokeColor = UIColor.systemBlueColor.CGColor;
    self.ripple.fillColor = UIColor.clearColor.CGColor;
    self.ripple.lineWidth = 0.2;
    [self.preview.layer addSublayer:self.ripple];
    CABasicAnimation *scale = [CABasicAnimation animationWithKeyPath:@"transform.scale"];
    scale.fromValue = @1; scale.toValue = @60;
    CABasicAnimation *fade = [CABasicAnimation animationWithKeyPath:@"opacity"];
    fade.fromValue = @1; fade.toValue = @0;
    CAAnimationGroup *group = [CAAnimationGroup animation];
    group.animations = @[scale, fade]; group.duration = 1.5; group.repeatCount = HUGE_VALF;
    [self.ripple addAnimation:group forKey:@"scanPulse"];
    [self.view setNeedsLayout];
}
- (void)showCameraUnavailable:(BOOL)denied {
    self.statusLabel.text = NSLocalizedString(denied ? @"Camera access is off. Enable it in Settings to scan QR codes." : @"No camera is available. Your saved history is still available.", nil);
    self.settingsButton.hidden = !denied;
    [self.ripple removeAllAnimations];
}
- (void)resumeCamera {
    if (!self.visible || self.hasResult || UIApplication.sharedApplication.applicationState != UIApplicationStateActive) return;
#if DEBUG
    NSArray *args = NSProcessInfo.processInfo.arguments;
    if ([args containsObject:@"-ui-testing"]) {
        [self showCameraUnavailable:[args containsObject:@"-camera-denied"]];
        return;
    }
#endif
    AVAuthorizationStatus status = [AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeVideo];
    if (status == AVAuthorizationStatusNotDetermined) {
        __weak typeof(self) weakSelf = self;
        [AVCaptureDevice requestAccessForMediaType:AVMediaTypeVideo completionHandler:^(BOOL granted) {
            dispatch_async(dispatch_get_main_queue(), ^{ [weakSelf resumeCamera]; });
        }];
        return;
    }
    if (status != AVAuthorizationStatusAuthorized) { [self showCameraUnavailable:YES]; return; }
    self.settingsButton.hidden = YES;
    self.statusLabel.text = NSLocalizedString(@"Point the camera at a QR code", nil);
    self.wantsCamera = YES;
    dispatch_async(self.sessionQueue, ^{
        if (!self.ready && ![self configureSession]) return;
        if (self.wantsCamera && !self.session.isRunning) [self.session startRunning];
    });
}
- (BOOL)configureSession {
    AVCaptureDevice *device = [AVCaptureDevice defaultDeviceWithMediaType:AVMediaTypeVideo];
    NSError *error;
    AVCaptureDeviceInput *input = device ? [AVCaptureDeviceInput deviceInputWithDevice:device error:&error] : nil;
    AVCaptureMetadataOutput *output = [AVCaptureMetadataOutput new];
    [self.session beginConfiguration];
    if (!input || ![self.session canAddInput:input]) {
        [self.session commitConfiguration];
        dispatch_async(dispatch_get_main_queue(), ^{ [self showCameraUnavailable:NO]; });
        return NO;
    }
    [self.session addInput:input];
    if (![self.session canAddOutput:output]) {
        [self.session removeInput:input];
        [self.session commitConfiguration];
        dispatch_async(dispatch_get_main_queue(), ^{ [self showCameraUnavailable:NO]; });
        return NO;
    }
    [self.session addOutput:output];
    if (![output.availableMetadataObjectTypes containsObject:AVMetadataObjectTypeQRCode]) {
        [self.session removeOutput:output]; [self.session removeInput:input];
        [self.session commitConfiguration];
        dispatch_async(dispatch_get_main_queue(), ^{ [self showCameraUnavailable:NO]; });
        return NO;
    }
    output.metadataObjectTypes = @[AVMetadataObjectTypeQRCode];
    [output setMetadataObjectsDelegate:self queue:dispatch_get_main_queue()];
    [self.session commitConfiguration];
    self.ready = YES;
    dispatch_async(dispatch_get_main_queue(), ^{
        self.previewLayer = [AVCaptureVideoPreviewLayer layerWithSession:self.session];
        self.previewLayer.videoGravity = AVLayerVideoGravityResizeAspectFill;
        [self.preview.layer insertSublayer:self.previewLayer atIndex:0];
        AVCaptureConnection *connection = self.previewLayer.connection;
        if (@available(iOS 17.0, *)) {
            if ([connection isVideoRotationAngleSupported:90]) connection.videoRotationAngle = 90;
        } else if (connection.isVideoOrientationSupported) {
            connection.videoOrientation = AVCaptureVideoOrientationPortrait;
        }
        [self.view setNeedsLayout];
    });
    return YES;
}
- (void)pauseCamera {
    self.wantsCamera = NO;
    dispatch_async(self.sessionQueue, ^{ if (self.session.isRunning) [self.session stopRunning]; });
}
- (void)captureInterrupted:(NSNotification *)notification {
    dispatch_async(dispatch_get_main_queue(), ^{ if (!self.hasResult) self.statusLabel.text = NSLocalizedString(@"Camera interrupted. Scanning will resume when available.", nil); });
}
- (void)captureFailed:(NSNotification *)notification {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (!self.hasResult) {
            self.statusLabel.text = NSLocalizedString(@"The camera could not start. Try scanning again.", nil);
            self.againButton.hidden = NO;
        }
    });
}
- (void)captureOutput:(AVCaptureOutput *)output didOutputMetadataObjects:(NSArray *)metadataObjects fromConnection:(AVCaptureConnection *)connection {
    if (!self.visible || self.hasResult || !self.wantsCamera) return;
    for (AVMetadataObject *object in metadataObjects) {
        if ([object.type isEqualToString:AVMetadataObjectTypeQRCode] && [object isKindOfClass:AVMetadataMachineReadableCodeObject.class]) {
            [self handlePayload:((AVMetadataMachineReadableCodeObject *)object).stringValue];
            break;
        }
    }
}
- (void)handlePayload:(NSString *)payload {
    if (self.hasResult) return;
    if (!payload.length) {
        self.hasResult = YES;
        [self pauseCamera];
        [self.ripple removeAllAnimations];
        self.statusLabel.text = NSLocalizedString(@"This QR code is empty or could not be read. Try another code.", nil);
        self.againButton.hidden = NO;
        return;
    }
    self.hasResult = YES;
    self.payload = payload;
    [self pauseCamera];
    [self.ripple removeAllAnimations];
    self.resultLabel.text = payload;
    self.resultLabel.hidden = self.againButton.hidden = self.resultCopyButton.hidden = NO;
    self.settingsButton.hidden = YES;
    self.openButton.hidden = [NSString HTTPURLFromString:payload] == nil;
    NSError *error;
    BOOL saved = [[AppDelegate appDelegate].historyStore recordPayload:payload error:&error];
    self.statusLabel.text = NSLocalizedString(saved ? @"QR code saved to History" : @"QR code read, but history could not be saved. Your existing history has not been erased.", nil);
    UIAccessibilityPostNotification(UIAccessibilityAnnouncementNotification, self.statusLabel.text);
}
- (void)scanAgain {
    self.hasResult = NO; self.payload = nil;
    self.resultLabel.hidden = self.openButton.hidden = self.resultCopyButton.hidden = self.againButton.hidden = YES;
    [self updateRipple]; [self resumeCamera];
}
- (void)copyResult { if (self.payload) UIPasteboard.generalPasteboard.string = self.payload; }
- (void)openWebsite {
    NSURL *URL = [NSString HTTPURLFromString:self.payload];
    if (!URL) return;
    [UIApplication.sharedApplication openURL:URL options:@{} completionHandler:^(BOOL success) {
        if (!success) self.statusLabel.text = NSLocalizedString(@"This website could not be opened.", nil);
    }];
}
- (void)openSettings {
    [UIApplication.sharedApplication openURL:[NSURL URLWithString:UIApplicationOpenSettingsURLString] options:@{} completionHandler:nil];
}
@end
