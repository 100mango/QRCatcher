#import "QRActionButton.h"
#import <math.h>
@implementation QRActionButton
- (CGSize)intrinsicContentSize {
    CGSize normal = [super intrinsicContentSize];
    CGFloat width = self.bounds.size.width;
    if (width <= 0) return normal;
    UIEdgeInsets insets = self.contentEdgeInsets;
    CGFloat available = MAX(1, width - insets.left - insets.right - 16);
    CGSize title = [self.titleLabel sizeThatFits:CGSizeMake(available, CGFLOAT_MAX)];
    return CGSizeMake(UIViewNoIntrinsicMetric, MAX(44, ceil(title.height) + insets.top + insets.bottom + 16));
}
- (void)setBounds:(CGRect)bounds {
    BOOL widthChanged = fabs(bounds.size.width - self.bounds.size.width) > 0.5;
    [super setBounds:bounds];
    if (widthChanged) [self invalidateIntrinsicContentSize];
}
- (void)traitCollectionDidChange:(UITraitCollection *)previous {
    [super traitCollectionDidChange:previous];
    [self invalidateIntrinsicContentSize];
}
- (CGRect)titleRectForContentRect:(CGRect)contentRect {
    CGRect title = CGRectInset(contentRect, 8, 8);
    title.size.width = MAX(0, title.size.width);
    title.size.height = MAX(0, title.size.height);
    return title;
}
@end
