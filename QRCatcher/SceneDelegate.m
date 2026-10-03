#import "SceneDelegate.h"
#import "AppDelegate.h"
#import "QRCatchViewController.h"
#import "QRURLViewController.h"
#import <SafariServices/SafariServices.h>
@implementation SceneDelegate
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)connectionOptions {
    if (![scene isKindOfClass:UIWindowScene.class]) return;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    QRCatchViewController *scan = [QRCatchViewController new];
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
    UIViewController *presenter = tabs.selectedViewController;
    if (presenter.presentedViewController) return;
    NSURL *URL = [NSURL URLWithString:@"https://100mango.github.io/app-privacy/"];
    SFSafariViewController *browser = [[SFSafariViewController alloc] initWithURL:URL];
    browser.dismissButtonStyle = SFSafariViewControllerDismissButtonStyleDone;
    browser.modalPresentationStyle = UIModalPresentationFullScreen;
    [presenter presentViewController:browser animated:YES completion:nil];
}
- (void)sceneDidEnterBackground:(UIScene *)scene { [[AppDelegate appDelegate] saveContext]; }
@end
