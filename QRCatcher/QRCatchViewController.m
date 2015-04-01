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

@interface QRCatchViewController ()<AVCaptureMetadataOutputObjectsDelegate>
@property (weak, nonatomic) IBOutlet UILabel *stringLabel;

@end

@implementation QRCatchViewController

#pragma mark View Life Cycle

- (void)viewDidLoad {
    [super viewDidLoad];
    
    //session
    AVCaptureSession *session = [[AVCaptureSession alloc] init];
    //device
    AVCaptureDevice *device = [AVCaptureDevice defaultDeviceWithMediaType:AVMediaTypeVideo];
    NSError *error = nil;
    //input
    AVCaptureDeviceInput *input = [AVCaptureDeviceInput deviceInputWithDevice:device error:&error];
    if(input) {
        [session addInput:input];
    } else {
        NSLog(@"%@", error);
        return;
    }
    //output
    AVCaptureMetadataOutput *output = [[AVCaptureMetadataOutput alloc] init];
    [output setMetadataObjectTypes:@[AVMetadataObjectTypeQRCode]];
    [output setMetadataObjectsDelegate:self queue:dispatch_get_main_queue()];
    [session addOutput:output];
    
    //add preview layer
    AVCaptureVideoPreviewLayer *previewLayer = [AVCaptureVideoPreviewLayer layerWithSession:session];
    previewLayer.frame = self.view.bounds;
    [self.view.layer addSublayer:previewLayer];
    
    //start
    [session startRunning];

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
            
            NSLog(@"%@",metadata.stringValue);
            if ([metadata.stringValue isURL])
            {
                [[UIApplication sharedApplication] openURL:[NSURL URLWithString:metadata.stringValue]];
            }
            else
            {
                self.stringLabel.text = metadata.stringValue;
            }
        }
    }
}


@end
