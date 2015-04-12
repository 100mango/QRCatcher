//
//  ViewController.m
//  QRCatcher
//
//  Created by Mango on 15/4/1.
//  Copyright (c) 2015年 Mango. All rights reserved.
//

#import "QRCatchViewController.h"
@import AVFoundation;
#import "NSString+Tools.h"
#import "AppDelegate.h"
#import "URLEntity.h"
#import "Masonry.h"

@interface QRCatchViewController ()<AVCaptureMetadataOutputObjectsDelegate>
@property (weak, nonatomic) IBOutlet UILabel *stringLabel;
@property (weak, nonatomic) IBOutlet UIView *preview;

//AVFoundation
@property (strong,nonatomic) AVCaptureSession *session;
@property (strong,nonatomic) AVCaptureVideoPreviewLayer *previewLayer;

@end

@implementation QRCatchViewController

#pragma mark View Life Cycle

- (void)viewDidLoad {
    [super viewDidLoad];
    
    //session
    self.session = [[AVCaptureSession alloc] init];
    //device
    AVCaptureDevice *device = [AVCaptureDevice defaultDeviceWithMediaType:AVMediaTypeVideo];
    NSError *error = nil;
    //input
    AVCaptureDeviceInput *input = [AVCaptureDeviceInput deviceInputWithDevice:device error:&error];
    if(input) {
        [self.session addInput:input];
    } else {
        NSLog(@"%@", error);
        return;
    }
    //output
    AVCaptureMetadataOutput *output = [[AVCaptureMetadataOutput alloc] init];
    [self.session addOutput:output];
    [output setMetadataObjectTypes:@[AVMetadataObjectTypeQRCode]];
    [output setMetadataObjectsDelegate:self queue:dispatch_get_main_queue()];
    
    //add preview layer
    self.previewLayer = [AVCaptureVideoPreviewLayer layerWithSession:self.session];
    [self.preview.layer addSublayer:self.previewLayer];

    
    //start
    [self.session startRunning];

}

- (void)viewDidLayoutSubviews
{
    [super viewDidLayoutSubviews];
    
    //previewLayer.videoGravity = AVLayerVideoGravityResizeAspectFill;
    self.previewLayer.bounds = self.preview.bounds;
    self.previewLayer.position = CGPointMake(CGRectGetMidX(self.preview.bounds), CGRectGetMidY(self.preview.bounds));
    
}

- (void)didReceiveMemoryWarning {
    [super didReceiveMemoryWarning];
    // Dispose of any resources that can be recreated.
}



#pragma mark - AVCaptureMetadataOutputObjectsDelegate
- (void)captureOutput:(AVCaptureOutput *)captureOutput didOutputMetadataObjects:(NSArray *)metadataObjects fromConnection:(AVCaptureConnection *)connection
{
    for (AVMetadataMachineReadableCodeObject *metadata in metadataObjects) {
        if ([metadata.type isEqualToString:AVMetadataObjectTypeQRCode]) {
            
            if ([metadata.stringValue isURL])
            {
                [[UIApplication sharedApplication] openURL:[NSURL URLWithString:metadata.stringValue]];
                [self insertURLEntityWithURL:metadata.stringValue];
            }
            else
            {
                self.stringLabel.text = metadata.stringValue;
            }
        }
    }
}

#pragma mark - core data
- (void)insertURLEntityWithURL:(NSString*)URL
{
    NSManagedObjectContext *context = [[AppDelegate appDelegate] managedObjectContext];
    
    //确保插入不重复URL
    if ([self getURLEntityWithURL:URL] == nil)
    {
        URLEntity *object = [NSEntityDescription insertNewObjectForEntityForName:@"URLEntity" inManagedObjectContext:context];
        object.url = URL;
        object.createDate = [NSDate date];
    }
}

- (URLEntity*)getURLEntityWithURL:(NSString*)URL
{
    NSManagedObjectContext *context = [[AppDelegate appDelegate] managedObjectContext];

    NSFetchRequest *requset = [NSFetchRequest fetchRequestWithEntityName:@"URLEntity"];
    NSPredicate *predicate = [NSPredicate predicateWithFormat:@"@K == %@",@"url",URL];
    requset.predicate = predicate;
    
    NSError *error = nil;
    NSArray *result = [context executeFetchRequest:requset error:&error];
    if (error) {
        NSLog(@"%@",error);
        return nil;
    }
    else
    {
        if (result && result.count > 0) {
            return result.firstObject;
        }
        else
        {
            return nil;
        }
    }
}

@end
