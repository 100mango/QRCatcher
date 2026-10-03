//
//  QRURLViewController.h
//  QRCatcher
//
//  Created by Mango on 15/4/7.
//  Copyright (c) 2015年 Mango. All rights reserved.
//

#import <UIKit/UIKit.h>

@interface QRURLViewController : UIViewController
@property (nonatomic, copy, nullable) void (^selectedPayloadHandler)(NSString *payload);

@end
