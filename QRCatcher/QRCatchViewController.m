#import "QRCatchViewController.h"
#import "AppDelegate.h"
#import "NSString+Tools.h"
#import "QRCodeCodec.h"
#import "QRImageCodec.h"
#import "QRImageImportQueue.h"
#import "QRActionButton.h"
#import <PhotosUI/PhotosUI.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#import <AVFoundation/AVFoundation.h>
#import <QuartzCore/QuartzCore.h>

@interface QRCatchViewController () <AVCaptureMetadataOutputObjectsDelegate, PHPickerViewControllerDelegate, UIDocumentPickerDelegate>
@property (nonatomic, strong) UIView *preview;
@property (nonatomic, strong) UIImageView *catcherIndicator;
@property (nonatomic, strong) UILabel *statusLabel;
@property (nonatomic, strong) UILabel *resultLabel;
@property (nonatomic, strong) UIButton *settingsButton;
@property (nonatomic, strong) UIButton *openButton;
@property (nonatomic, strong) UIButton *againButton;
@property (nonatomic, strong) UIButton *resultCopyButton;
@property (nonatomic, strong) UIButton *importButton;
@property (nonatomic, strong) UIButton *shareButton;
@property (nonatomic) BOOL importing;
@property (nonatomic) NSUInteger importGeneration;
@property (nonatomic, strong) NSOperation *importOperation;
@property (nonatomic, strong) NSProgress *photoProgress;
@property (nonatomic, strong) CAShapeLayer *ripple;
@property (nonatomic, strong) AVCaptureSession *session;
@property (nonatomic, strong) AVCaptureVideoPreviewLayer *previewLayer;
@property (nonatomic, strong) dispatch_queue_t sessionQueue;
@property (atomic) BOOL visible;
@property (atomic) BOOL ready;
@property (atomic) BOOL wantsCamera;
@property (nonatomic) BOOL hasResult;
@property (nonatomic) BOOL privacyPolicyPresented;
@property (nonatomic) BOOL appliedFixture;
@property (nonatomic, copy) NSString *payload;
#if DEBUG
@property (atomic) NSUInteger cameraDiagnosticEpoch;
#endif
@end

@implementation QRCatchViewController
- (UIButton *)button:(NSString *)title identifier:(NSString *)identifier action:(SEL)action {
    UIButton *button = [QRActionButton buttonWithType:UIButtonTypeSystem];
    [button setTitle:NSLocalizedString(title, nil) forState:UIControlStateNormal];
    button.titleLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleHeadline];
    button.titleLabel.adjustsFontForContentSizeCategory = YES;
    button.titleLabel.numberOfLines = 0;
    button.titleLabel.adjustsFontSizeToFitWidth = NO;
    [button setContentCompressionResistancePriority:UILayoutPriorityRequired - 1 forAxis:UILayoutConstraintAxisVertical];
    button.titleLabel.lineBreakMode = NSLineBreakByWordWrapping;
    button.titleLabel.textAlignment = NSTextAlignmentCenter;
    button.accessibilityIdentifier = identifier;
    if (action) [button addTarget:self action:action forControlEvents:UIControlEventTouchUpInside];
    NSLayoutConstraint *minimumHeight = [button.heightAnchor constraintGreaterThanOrEqualToConstant:44];
    // Hidden arranged subviews must be allowed to collapse without conflicting with UIStackView.
    minimumHeight.priority = UILayoutPriorityRequired - 1;
    minimumHeight.active = YES;
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
    self.importButton = [self button:@"Import Image" identifier:@"scan.import" action:NULL];
    __weak typeof(self) weakSelf = self;
    self.importButton.menu = [UIMenu menuWithChildren:@[
        [UIAction actionWithTitle:NSLocalizedString(@"Photo Library", nil) image:[UIImage systemImageNamed:@"photo"] identifier:nil handler:^(UIAction *action) { [weakSelf choosePhoto]; }],
        [UIAction actionWithTitle:NSLocalizedString(@"Choose File", nil) image:[UIImage systemImageNamed:@"folder"] identifier:nil handler:^(UIAction *action) { [weakSelf chooseFile]; }]
    ]];
    self.importButton.showsMenuAsPrimaryAction = YES;
    self.shareButton = [self button:@"Share QR Image" identifier:@"scan.share" action:@selector(shareResult)];
    self.shareButton.hidden = YES;
    self.againButton = [self button:@"Scan Again" identifier:@"scan.again" action:@selector(scanAgain)];
    self.settingsButton.hidden = self.openButton.hidden = self.againButton.hidden = self.resultCopyButton.hidden = YES;
    UIStackView *stack = [[UIStackView alloc] initWithArrangedSubviews:@[self.preview, self.statusLabel, self.resultLabel, self.settingsButton, self.openButton, self.resultCopyButton, self.shareButton, self.againButton, self.importButton]];
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
- (void)dealloc { [self.photoProgress cancel]; [self.importOperation cancel]; [NSNotificationCenter.defaultCenter removeObserver:self]; }
- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];
    self.previewLayer.frame = self.preview.bounds;
    [self updatePreviewOrientation];
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
#if DEBUG
- (void)traceCamera:(NSString *)event {
    if (!NSThread.isMainThread) {
        __weak typeof(self) weakSelf = self;
        dispatch_async(dispatch_get_main_queue(), ^{ [weakSelf traceCamera:event]; });
        return;
    }
    // Debug-only AX diagnostics survive a failing UI test even when the app's
    // console is not forwarded into xcodebuild's UI-runner output.
    self.statusLabel.accessibilityValue = [NSString stringWithFormat:@"event=%@ epoch=%lu authorization=%ld scene=%ld app=%ld visible=%d ready=%d wants=%d", event,
        (unsigned long)self.cameraDiagnosticEpoch, (long)[AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeVideo],
        (long)self.view.window.windowScene.activationState, (long)UIApplication.sharedApplication.applicationState, self.visible, self.ready, self.wantsCamera];
    NSLog(@"QRCATCHER_CAMERA_TRACE event=%@ epoch=%lu authorization=%ld scene=%ld app=%ld visible=%d result=%d importing=%d presented=%@ policy=%d ready=%d wants=%d status=%@",
          event, (unsigned long)self.cameraDiagnosticEpoch, (long)[AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeVideo],
          (long)self.view.window.windowScene.activationState, (long)UIApplication.sharedApplication.applicationState,
          self.visible, self.hasResult, self.importing, NSStringFromClass(self.presentedViewController.class), self.privacyPolicyPresented,
          self.ready, self.wantsCamera, self.statusLabel.text);
}
#endif
- (void)showCameraUnavailable:(BOOL)denied {
    self.statusLabel.text = NSLocalizedString(denied ? @"Camera access is off. Enable it in Settings to scan QR codes." : @"No camera is available. Your saved history is still available.", nil);
    self.settingsButton.hidden = !denied;
#if DEBUG
    [self traceCamera:denied ? @"denied-visible" : @"unavailable-visible"];
#endif
    [self.ripple removeAllAnimations];
}
- (void)setPrivacyPolicyPresented:(BOOL)presented {
    _privacyPolicyPresented = presented;
    if (!self.isViewLoaded) return;
    if (presented) [self pauseCamera]; else [self resumeCamera];
}
- (void)resumeCamera {
#if DEBUG
    self.cameraDiagnosticEpoch += 1;
    [self traceCamera:@"resume-enter"];
#endif
    if (!self.visible || self.hasResult || self.importing || self.privacyPolicyPresented || self.presentedViewController) return;
#if DEBUG
    // Hosted unit tests do not exercise camera hardware. Avoid a system permission
    // alert competing with the separate UI-test runner's automation session.
    if (NSClassFromString(@"XCTestCase") != nil) {
        [self.ripple removeAllAnimations];
        return;
    }
    NSArray *args = NSProcessInfo.processInfo.arguments;
    if ([args containsObject:@"-ui-testing"]) {
        [self showCameraUnavailable:[args containsObject:@"-camera-denied"]];
        return;
    }
#endif
    if (self.view.window.windowScene.activationState != UISceneActivationStateForegroundActive) return;
    AVAuthorizationStatus status = [AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeVideo];
    if (status == AVAuthorizationStatusNotDetermined) {
        __weak typeof(self) weakSelf = self;
#if DEBUG
        NSUInteger requestedEpoch = self.cameraDiagnosticEpoch;
        [self traceCamera:@"request-system-authorization"];
#endif
        [AVCaptureDevice requestAccessForMediaType:AVMediaTypeVideo completionHandler:^(BOOL granted) {
            dispatch_async(dispatch_get_main_queue(), ^{
#if DEBUG
                [weakSelf traceCamera:[NSString stringWithFormat:@"authorization-callback granted=%d requestedEpoch=%lu", granted, (unsigned long)requestedEpoch]];
#endif
                [weakSelf resumeCamera];
            });
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
#if DEBUG
    NSLog(@"QRCATCHER_CAMERA_TRACE configure epoch=%lu device=%@ input=%d error=%@ running=%d", (unsigned long)self.cameraDiagnosticEpoch, device.deviceType, input != nil, error, self.session.isRunning);
#endif
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
        [self updatePreviewOrientation];
        [self.view setNeedsLayout];
    });
    return YES;
}
// Use the window's orientation, not the physical device orientation. This also
// works while an iPad window is resized or a keyboard keeps the device upright.
+ (CGFloat)previewRotationForOrientation:(UIInterfaceOrientation)orientation {
    switch (orientation) {
        case UIInterfaceOrientationLandscapeLeft: return 0;
        case UIInterfaceOrientationLandscapeRight: return 180;
        case UIInterfaceOrientationPortraitUpsideDown: return 270;
        default: return 90;
    }
}
- (void)updatePreviewOrientation {
    AVCaptureConnection *connection = self.previewLayer.connection;
    UIInterfaceOrientation orientation = self.view.window.windowScene.interfaceOrientation;
    if (@available(iOS 17.0, *)) {
        CGFloat angle = [self.class previewRotationForOrientation:orientation];
        if ([connection isVideoRotationAngleSupported:angle]) connection.videoRotationAngle = angle;
    } else if (connection.isVideoOrientationSupported) {
        switch (orientation) {
            case UIInterfaceOrientationLandscapeLeft: connection.videoOrientation = AVCaptureVideoOrientationLandscapeLeft; break;
            case UIInterfaceOrientationLandscapeRight: connection.videoOrientation = AVCaptureVideoOrientationLandscapeRight; break;
            case UIInterfaceOrientationPortraitUpsideDown: connection.videoOrientation = AVCaptureVideoOrientationPortraitUpsideDown; break;
            default: connection.videoOrientation = AVCaptureVideoOrientationPortrait;
        }
    }
}
- (void)viewWillTransitionToSize:(CGSize)size withTransitionCoordinator:(id<UIViewControllerTransitionCoordinator>)coordinator {
    [super viewWillTransitionToSize:size withTransitionCoordinator:coordinator];
    [coordinator animateAlongsideTransition:^(id<UIViewControllerTransitionCoordinatorContext> context) {
        [self updatePreviewOrientation];
        [self.view setNeedsLayout];
    } completion:nil];
}
- (void)pauseCamera {
#if DEBUG
    self.cameraDiagnosticEpoch += 1;
    [self traceCamera:@"pause"];
#endif
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
    if (!self.visible || self.hasResult || self.privacyPolicyPresented || self.presentedViewController || self.importing || !self.wantsCamera) return;
    for (AVMetadataObject *object in metadataObjects) {
        if ([object.type isEqualToString:AVMetadataObjectTypeQRCode] && [object isKindOfClass:AVMetadataMachineReadableCodeObject.class]) {
            [self handlePayload:((AVMetadataMachineReadableCodeObject *)object).stringValue];
            break;
        }
    }
}
- (void)handlePayload:(NSString *)payload { [self displayPayload:payload saveToHistory:YES]; }
- (void)showSavedPayload:(NSString *)payload {
    [self loadViewIfNeeded];
    [self.importOperation cancel]; [self.photoProgress cancel];
    self.importGeneration += 1; self.importing = NO;
    self.hasResult = NO;
    [self displayPayload:payload saveToHistory:NO];
}
- (void)displayPayload:(NSString *)payload saveToHistory:(BOOL)save {
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
    self.resultLabel.hidden = self.againButton.hidden = self.resultCopyButton.hidden = self.shareButton.hidden = NO;
    self.settingsButton.hidden = YES;
    self.openButton.hidden = [NSString HTTPURLFromString:payload] == nil;
    NSError *error;
    BOOL saved = !save || [[AppDelegate appDelegate].historyStore recordPayload:payload error:&error];
    self.statusLabel.text = NSLocalizedString(saved ? @"QR code saved to History" : @"QR code read, but history could not be saved. Your existing history has not been erased.", nil);
    UIAccessibilityPostNotification(UIAccessibilityAnnouncementNotification, self.statusLabel.text);
}
- (void)scanAgain {
    [self.importOperation cancel]; [self.photoProgress cancel];
    self.importGeneration += 1; self.importing = NO;
    self.hasResult = NO; self.payload = nil;
    self.resultLabel.hidden = self.openButton.hidden = self.resultCopyButton.hidden = self.shareButton.hidden = self.againButton.hidden = YES;
    [self updateRipple]; [self resumeCamera];
}
- (NSArray<UIKeyCommand *> *)keyCommands {
    return @[
        [UIKeyCommand keyCommandWithInput:@"c" modifierFlags:UIKeyModifierCommand action:@selector(copyResult)],
        [UIKeyCommand keyCommandWithInput:@"n" modifierFlags:UIKeyModifierCommand action:@selector(scanAgain)],
        [UIKeyCommand keyCommandWithInput:@"o" modifierFlags:UIKeyModifierCommand action:@selector(chooseFile)]
    ];
}
- (void)choosePhoto {
    if (self.presentedViewController) return;
    [self.importOperation cancel]; [self.photoProgress cancel];
    self.importGeneration += 1; self.importing = YES; [self pauseCamera];
    PHPickerConfiguration *configuration = [[PHPickerConfiguration alloc] init];
    configuration.filter = PHPickerFilter.imagesFilter; configuration.selectionLimit = 1;
    PHPickerViewController *picker = [[PHPickerViewController alloc] initWithConfiguration:configuration];
    picker.delegate = self;
    [self presentViewController:picker animated:YES completion:nil];
}
- (void)chooseFile {
    if (self.presentedViewController) return;
    [self.importOperation cancel]; [self.photoProgress cancel];
    self.importGeneration += 1; self.importing = YES; [self pauseCamera];
    UIDocumentPickerViewController *picker = [[UIDocumentPickerViewController alloc] initForOpeningContentTypes:@[UTTypeImage] asCopy:NO];
    picker.delegate = self; picker.allowsMultipleSelection = NO;
    [self presentViewController:picker animated:YES completion:nil];
}
- (void)documentPickerWasCancelled:(UIDocumentPickerViewController *)controller { self.importing = NO; [self resumeCamera]; }
- (void)documentPicker:(UIDocumentPickerViewController *)controller didPickDocumentsAtURLs:(NSArray<NSURL *> *)URLs {
    NSURL *URL = URLs.firstObject;
    if (!URL) { self.importing = NO; [self resumeCamera]; return; }
    NSUInteger generation = self.importGeneration;
    __weak typeof(self) weakSelf = self;
    self.importOperation = [QRImageImportQueue readWithLoader:^NSData *(NSError **error) {
        BOOL access = [URL startAccessingSecurityScopedResource];
        NSNumber *size; [URL getResourceValue:&size forKey:NSURLFileSizeKey error:error];
        NSData *data = (size.unsignedLongLongValue <= 50 * 1024 * 1024) ? [NSData dataWithContentsOfURL:URL options:NSDataReadingMappedIfSafe error:error] : nil;
        if (access) [URL stopAccessingSecurityScopedResource];
        return data;
    } completion:^(NSArray<NSString *> *values, NSError *error) {
        [weakSelf finishImportedValues:values error:error generation:generation];
    }];
}

- (void)picker:(PHPickerViewController *)picker didFinishPicking:(NSArray<PHPickerResult *> *)results {
    [picker dismissViewControllerAnimated:YES completion:^{ if (!results.count) { self.importing = NO; [self resumeCamera]; } }];
    if (!results.count) return;
    NSUInteger generation = self.importGeneration;
    NSItemProvider *provider = results.firstObject.itemProvider;
    NSString *type = nil;
    for (NSString *identifier in provider.registeredTypeIdentifiers) {
        if ([[UTType typeWithIdentifier:identifier] conformsToType:UTTypeImage]) { type = identifier; break; }
    }
    if (!type) { [self decodeImportedData:nil generation:generation]; return; }
    self.photoProgress = [provider loadDataRepresentationForTypeIdentifier:type completionHandler:^(NSData *data, NSError *error) {
        [self decodeImportedData:data generation:generation];
    }];
}
- (void)decodeImportedData:(NSData *)data generation:(NSUInteger)generation {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (generation != self.importGeneration) return;
        __weak typeof(self) weakSelf = self;
        self.importOperation = [QRImageImportQueue readWithLoader:^NSData *(NSError **error) { return data; } completion:^(NSArray<NSString *> *values, NSError *error) {
            [weakSelf finishImportedValues:values error:error generation:generation];
        }];
    });
}
- (void)finishImportedValues:(NSArray<NSString *> *)values error:(NSError *)error generation:(NSUInteger)generation {
    if (generation != self.importGeneration) return;
    self.importing = NO;
    if (!values.count) {
        self.statusLabel.text = NSLocalizedString(values && !error ? @"No QR code was found. Try a clearer image." : @"This image could not be read. Choose an image smaller than 50 MB.", nil);
        self.againButton.hidden = NO;
        return;
    }
    self.hasResult = NO;
    [self handlePayload:values.firstObject];
    for (NSString *payload in [values subarrayWithRange:NSMakeRange(1, values.count - 1)]) {
        NSError *saveError;
        if (![[AppDelegate appDelegate].historyStore recordPayload:payload error:&saveError]) self.statusLabel.text = NSLocalizedString(@"QR code read, but history could not be saved. Your existing history has not been erased.", nil);
    }
}
- (void)shareResult {
    if (!self.payload || self.presentedViewController) return;
    NSData *PNG = [QRImageCodec PNGForPayload:self.payload];
    UIImage *image = PNG ? [UIImage imageWithData:PNG] : nil;
    if (!image) { self.statusLabel.text = NSLocalizedString(@"This result could not be exported as a QR image.", nil); return; }
    UIActivityViewController *activity = [[UIActivityViewController alloc] initWithActivityItems:@[image, self.payload] applicationActivities:nil];
    activity.popoverPresentationController.sourceView = self.shareButton;
    activity.popoverPresentationController.sourceRect = self.shareButton.bounds;
    [self presentViewController:activity animated:YES completion:nil];
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
