// Synthetic test infrastructure. This is not any of the three product apps.
#import <UIKit/UIKit.h>
@interface HarnessController : UIViewController
@property(nonatomic,strong) UILabel *status;
@end
@implementation HarnessController
- (void)viewDidLoad {
    [super viewDidLoad]; self.view.backgroundColor=UIColor.systemBackgroundColor;
    self.status=[UILabel new]; self.status.text=@"Harness ready";
    self.status.accessibilityIdentifier=@"harness.status";
    self.status.textAlignment=NSTextAlignmentCenter;
    UIButton *button=[UIButton buttonWithType:UIButtonTypeSystem];
    [button setTitle:@"Check interaction" forState:UIControlStateNormal];
    button.accessibilityIdentifier=@"harness.check";
    [button addTarget:self action:@selector(check) forControlEvents:UIControlEventTouchUpInside];
    UIStackView *stack=[[UIStackView alloc] initWithArrangedSubviews:@[self.status,button]];
    stack.axis=UILayoutConstraintAxisVertical; stack.spacing=16;
    stack.translatesAutoresizingMaskIntoConstraints=NO; [self.view addSubview:stack];
    [NSLayoutConstraint activateConstraints:@[
      [stack.centerXAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.centerXAnchor],
      [stack.centerYAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.centerYAnchor],
      [stack.widthAnchor constraintLessThanOrEqualToAnchor:self.view.safeAreaLayoutGuide.widthAnchor constant:-32],
      [button.heightAnchor constraintGreaterThanOrEqualToConstant:44]]];
}
- (void)check { self.status.text=@"Interaction verified"; }
@end
@interface HarnessDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic,strong) UIWindow *window;
@end
@implementation HarnessDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
    self.window=[[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    self.window.rootViewController=[HarnessController new]; [self.window makeKeyAndVisible]; return YES;
}
@end
int main(int argc,char **argv) { @autoreleasepool { return UIApplicationMain(argc,argv,nil,NSStringFromClass(HarnessDelegate.class)); } }
