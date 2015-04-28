//
//  QRTabBar.m
//  QRCatcher
//
//  Created by Mango on 15/4/21.
//  Copyright (c) 2015年 Mango. All rights reserved.
//

#import "QRTabBar.h"

@implementation QRTabBar

//修改tab bar 高度
-(CGSize)sizeThatFits:(CGSize)size
{
    CGSize sizeThatFits = [super sizeThatFits:size];
    sizeThatFits.height = 60;
    
    return sizeThatFits;
}


@end
