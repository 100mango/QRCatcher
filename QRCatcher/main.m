//
//  main.m
//  QRCatcher
//
//  Created by Mango on 15/4/1.
//  Copyright (c) 2015年 Mango. All rights reserved.
//

#import <UIKit/UIKit.h>
#import "AppDelegate.h"
#if DEBUG
#import <CoreFoundation/CFDate.h>
#endif

int main(int argc, char * argv[]) {
    @autoreleasepool {
#if DEBUG
        QRStartupObservationBegin(CFAbsoluteTimeGetCurrent());
#endif
        return UIApplicationMain(argc, argv, nil, NSStringFromClass([AppDelegate class]));
    }
}
