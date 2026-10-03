#import "QRActionButton.h"
#import <math.h>
@implementation QRActionButton
- (CGSize)intrinsicContentSize {
    CGFloat width = self.bounds.size.width;
    UIEdgeInsets insets = self.contentEdgeInsets;
    CGFloat available = MAX(1, width - insets.left - insets.right - 16);
    UIFont *font = self.titleLabel.font ?: [UIFont preferredFontForTextStyle:UIFontTextStyleHeadline];
    if (width <= 16) return CGSizeMake(UIViewNoIntrinsicMetric, MAX(44, ceil(font.lineHeight) + insets.top + insets.bottom + 16));
    NSMutableParagraphStyle *paragraph = [NSMutableParagraphStyle new];
    paragraph.lineBreakMode = NSLineBreakByWordWrapping;
    // Measure currentTitle directly: UIButton may not have copied it into its
    // internal UILabel when the stack first asks for intrinsic dimensions.
    CGRect text = [(self.currentTitle ?: @"") boundingRectWithSize:CGSizeMake(available, CGFLOAT_MAX)
        options:NSStringDrawingUsesLineFragmentOrigin | NSStringDrawingUsesFontLeading
        attributes:@{NSFontAttributeName:font, NSParagraphStyleAttributeName:paragraph} context:nil];
    CGSize label = [self.titleLabel sizeThatFits:CGSizeMake(available, CGFLOAT_MAX)];
    CGFloat fullHeight = MAX(font.lineHeight, MAX(text.size.height, label.height));
    return CGSizeMake(UIViewNoIntrinsicMetric, MAX(44, ceil(fullHeight) + insets.top + insets.bottom + 16));
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
- (CGRect)contentRectForBounds:(CGRect)bounds { return UIEdgeInsetsInsetRect(bounds, self.contentEdgeInsets); }
- (CGRect)titleRectForContentRect:(CGRect)contentRect {
    CGRect title = CGRectInset(contentRect, 8, 8);
    title.size.width = MAX(0, title.size.width);
    title.size.height = MAX(0, title.size.height);
    return title;
}
- (void)layoutSubviews {
    [super layoutSubviews];
    // Keep the measured and rendered content rectangles identical. UIKit's
    // default system-button content rectangle added another vertical inset,
    // clipping ~11 pt at AX XXXL even though the entire button was reachable.
    self.titleLabel.frame = [self titleRectForContentRect:[self contentRectForBounds:self.bounds]];
}
@end
