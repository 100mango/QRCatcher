#import "SceneDelegate.h"
#import "AppDelegate.h"
#import "QRCatchViewController.h"
#import "QRURLViewController.h"
@implementation SceneDelegate
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)connectionOptions {
    if (![scene isKindOfClass:UIWindowScene.class]) return;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    QRCatchViewController *scan = [QRCatchViewController new];
    QRURLViewController *history = [QRURLViewController new];
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
- (void)sceneDidEnterBackground:(UIScene *)scene { [[AppDelegate appDelegate] saveContext]; }
@end
