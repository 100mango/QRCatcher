#import "SceneDelegate.h"
#import "AppDelegate.h"
#import "QRCatchViewController.h"
#import "QRURLViewController.h"
#import <SafariServices/SafariServices.h>
@interface SceneDelegate () <SFSafariViewControllerDelegate, UIAdaptivePresentationControllerDelegate>
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
        UIBarButtonItem *privacy = [[UIBarButtonItem alloc] initWithTitle:NSLocalizedString(@"Privacy Policy", nil) style:UIBarButtonItemStylePlain target:self action:@selector(showPrivacyPolicy)];
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
    UITabBarController *tabs = [UITabBarController new];
    tabs.viewControllers = @[scanNav, historyNav];
    self.window.tintColor = UIColor.systemBlueColor;
    self.window.rootViewController = tabs;
    [self.window makeKeyAndVisible];
}
- (void)showPrivacyPolicy {
    UITabBarController *tabs = (UITabBarController *)self.window.rootViewController;
    UINavigationController *navigation = (UINavigationController *)tabs.selectedViewController;
    UIViewController *presenter = navigation.visibleViewController;
    if (presenter.presentedViewController) return;
    NSURL *URL = [NSURL URLWithString:@"https://100mango.github.io/app-privacy/"];
    SFSafariViewController *browser = [[SFSafariViewController alloc] initWithURL:URL];
    browser.dismissButtonStyle = SFSafariViewControllerDismissButtonStyleClose;
    browser.delegate = self;
    [self.scanController setPrivacyPolicyPresented:YES];
    [presenter presentViewController:browser animated:YES completion:^{
        browser.presentationController.delegate = self;
    }];
}
- (void)safariViewControllerDidFinish:(SFSafariViewController *)controller {
    [controller dismissViewControllerAnimated:YES completion:^{
        [self.scanController setPrivacyPolicyPresented:NO];
    }];
}
- (void)presentationControllerDidDismiss:(UIPresentationController *)presentationController {
    [self.scanController setPrivacyPolicyPresented:NO];
}
- (void)sceneDidEnterBackground:(UIScene *)scene { [[AppDelegate appDelegate] saveContext]; }
@end
