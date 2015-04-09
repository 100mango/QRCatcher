//
//  URLEntity.h
//  QRCatcher
//
//  Created by Mango on 15/4/8.
//  Copyright (c) 2015年 Mango. All rights reserved.
//

#import <Foundation/Foundation.h>
#import <CoreData/CoreData.h>


@interface URLEntity : NSManagedObject

@property (nonatomic, retain) NSString * url;
@property (nonatomic, retain) NSDate * createDate;

@end
