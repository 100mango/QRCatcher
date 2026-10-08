#import "QRPadSplitViewController.h"
@implementation QRPadSplitViewController
- (instancetype)init {
    if ((self = [super initWithStyle:UISplitViewControllerStyleDoubleColumn])) {
        self.delegate = self;
        self.preferredDisplayMode = UISplitViewControllerDisplayModeOneBesideSecondary;
        self.preferredSplitBehavior = UISplitViewControllerSplitBehaviorTile;
        self.minimumPrimaryColumnWidth = 240;
        self.maximumPrimaryColumnWidth = 380;
        self.preferredPrimaryColumnWidthFraction = 0.32;
    }
    return self;
}
- (UISplitViewControllerColumn)splitViewController:(UISplitViewController *)controller topColumnForCollapsingToProposedTopColumn:(UISplitViewControllerColumn)proposedTopColumn {
    return UISplitViewControllerColumnSecondary;
}
@end
