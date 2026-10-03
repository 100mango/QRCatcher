#import "SceneDelegate.h"
#import "AppDelegate.h"
#import "QRCatchViewController.h"
#import "QRURLViewController.h"
#import "QRPrivacyViewController.h"
#import "QRPadSplitViewController.h"
@interface SceneDelegate ()
@property (nonatomic, weak) QRCatchViewController *scanController;
@end
@implementation SceneDelegate
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)connectionOptions {
    if (![scene isKindOfClass:UIWindowScene.class]) return;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    QRCatchViewController *scan = [QRCatchViewController new];
    self.scanController = scan;
    QRURLViewController *history = [QRURLViewController new];
    for (UIViewController *controller in @[scan, history]) {
        UIBarButtonItem *privacy;
        if (UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPad) {
            privacy = [[UIBarButtonItem alloc] initWithImage:[UIImage systemImageNamed:@"hand.raised"] style:UIBarButtonItemStylePlain target:self action:@selector(showPrivacyPolicy)];
        } else {
            privacy = [[UIBarButtonItem alloc] initWithTitle:NSLocalizedString(@"Privacy Policy", nil) style:UIBarButtonItemStylePlain target:self action:@selector(showPrivacyPolicy)];
        }
        privacy.accessibilityLabel = NSLocalizedString(@"Privacy Policy", nil);
        privacy.accessibilityIdentifier = @"privacy.policy";
        controller.navigationItem.rightBarButtonItem = privacy;
    }
    UINavigationController *scanNav = [[UINavigationController alloc] initWithRootViewController:scan];
    UINavigationController *historyNav = [[UINavigationController alloc] initWithRootViewController:history];
    scanNav.tabBarItem = [[UITabBarItem alloc] initWithTitle:NSLocalizedString(@"Scan", nil) image:[UIImage imageNamed:@"catcher6_0003_scan_white_2x"] selectedImage:[UIImage imageNamed:@"catcher6_0004_scan_blue_2x"]];
    historyNav.tabBarItem = [[UITabBarItem alloc] initWithTitle:NSLocalizedString(@"History", nil) image:[UIImage imageNamed:@"catcher6_0001_history_white_2x"] selectedImage:[UIImage imageNamed:@"catcher6_0002_history_blue_2x"]];
    scanNav.tabBarItem.accessibilityIdentifier = @"scan.tab";
    historyNav.tabBarItem.accessibilityIdentifier = @"history.tab";
    self.window.tintColor = UIColor.systemBlueColor;
    if (UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPad) {
        QRPadSplitViewController *split = [QRPadSplitViewController new];
        [split setViewController:historyNav forColumn:UISplitViewControllerColumnPrimary];
        [split setViewController:scanNav forColumn:UISplitViewControllerColumnSecondary];
        __weak QRCatchViewController *weakScan = scan;
        __weak QRPadSplitViewController *weakSplit = split;
        history.selectedPayloadHandler = ^(NSString *payload) {
            [weakScan showSavedPayload:payload];
            [weakSplit showColumn:UISplitViewControllerColumnSecondary];
        };
        self.window.rootViewController = split;
    } else {
        UITabBarController *tabs = [UITabBarController new];
        tabs.viewControllers = @[scanNav, historyNav];
        self.window.rootViewController = tabs;
    }
    [self.window makeKeyAndVisible];
}
- (void)showPrivacyPolicy {
    UIViewController *presenter = self.window.rootViewController;
    if (presenter.presentedViewController) return;
    QRPrivacyViewController *privacy = [QRPrivacyViewController new];
    __weak typeof(self) weakSelf = self;
    privacy.dismissalHandler = ^{ [weakSelf.scanController setPrivacyPolicyPresented:NO]; };
    UINavigationController *policyNavigation = [[UINavigationController alloc] initWithRootViewController:privacy];
    policyNavigation.modalPresentationStyle = UIModalPresentationFullScreen;
    [self.scanController setPrivacyPolicyPresented:YES];
    [presenter presentViewController:policyNavigation animated:YES completion:nil];
}
- (void)sceneDidEnterBackground:(UIScene *)scene { [[AppDelegate appDelegate] saveContext]; }
@end
