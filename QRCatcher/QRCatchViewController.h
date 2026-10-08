//
//  ViewController.h
//  QRCatcher
//
//  Created by Mango on 15/4/1.
//  Copyright (c) 2015年 Mango. All rights reserved.
//

#import <UIKit/UIKit.h>

@interface QRCatchViewController : UIViewController
- (void)setPrivacyPolicyPresented:(BOOL)presented;
- (void)showSavedPayload:(NSString *)payload;
+ (CGFloat)previewRotationForOrientation:(UIInterfaceOrientation)orientation;


@end

