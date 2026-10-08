#import <XCTest/XCTest.h>
#import "QRWatchPhoneService.h"
#import "QRWatchSessionGate.h"
#import <CommonCrypto/CommonDigest.h>
@interface QRWatchPhoneServiceTests : XCTestCase @end
@implementation QRWatchPhoneServiceTests
- (NSDictionary *)requestForImage:(NSString *)name {
    NSURL *url = [[NSBundle bundleForClass:self.class] URLForResource:name withExtension:@"png"];
    NSData *image = [NSData dataWithContentsOfURL:url]; XCTAssertNotNil(image);
    unsigned char digest[CC_SHA256_DIGEST_LENGTH]; CC_SHA256(image.bytes, (CC_LONG)image.length, digest);
    NSMutableString *hash = [NSMutableString string]; for (NSUInteger i = 0; i < sizeof(digest); i++) [hash appendFormat:@"%02x", digest[i]];
    return @{@"kind":@"qrcatcher.decode.request", @"version":@1, @"recordID":NSUUID.UUID.UUIDString, @"requestID":NSUUID.UUID.UUIDString, @"sourceSHA256":hash, @"source":[image base64EncodedStringWithOptions:0]};
}
- (void)testRealPhoneProcessorUnicodeAndRotationWithoutHistoryWrite {
    for (NSString *name in @[@"unicode", @"rotated"]) {
        NSDictionary *request = [self requestForImage:name];
        NSData *json = [NSJSONSerialization dataWithJSONObject:request options:0 error:nil];
        NSData *response = [QRWatchPhoneService.shared decodedResponseForRequestData:json]; XCTAssertNotNil(response);
        NSDictionary *value = [NSJSONSerialization JSONObjectWithData:response options:0 error:nil];
        XCTAssertEqualObjects(value[@"payloads"], (@[@"QRCatcher 你好 🌈 123"]));
        XCTAssertEqualObjects(value[@"recordID"], request[@"recordID"]); XCTAssertEqualObjects(value[@"requestID"], request[@"requestID"]);
        XCTAssertEqualObjects(value[@"sourceSHA256"], request[@"sourceSHA256"]);
    }
}
- (void)testInactiveAndCounterpartSwitchSuppressStaleDecodeDelivery {
    QRWatchSessionGate *gate = [QRWatchSessionGate new]; __block NSUInteger deliveries = 0;
    NSUInteger first = [gate activateCounterpart];
    XCTAssertTrue([gate performIfCurrent:first block:^{ deliveries++; }]);
    [gate invalidate];
    XCTAssertFalse([gate performIfCurrent:first block:^{ deliveries++; }]);
    NSUInteger second = [gate activateCounterpart]; XCTAssertNotEqual(first, second);
    XCTAssertFalse([gate performIfCurrent:first block:^{ deliveries++; }]);
    XCTAssertTrue([gate performIfCurrent:second block:^{ deliveries++; }]); XCTAssertEqual(deliveries, 2);
}
- (void)testDuplicateIDAcceptsOnlyIdenticalFingerprintAndRecord {
    NSDictionary *request = [self requestForImage:@"unicode"];
    NSData *original = [NSJSONSerialization dataWithJSONObject:request options:0 error:nil];
    XCTAssertTrue([QRWatchPhoneService.shared requestData:original matchesRequest:original]);
    NSMutableDictionary *changed = [request mutableCopy]; changed[@"sourceSHA256"] = @"different fingerprint";
    XCTAssertFalse([QRWatchPhoneService.shared requestData:original matchesRequest:[NSJSONSerialization dataWithJSONObject:changed options:0 error:nil]]);
    changed = [request mutableCopy]; changed[@"recordID"] = NSUUID.UUID.UUIDString;
    XCTAssertFalse([QRWatchPhoneService.shared requestData:original matchesRequest:[NSJSONSerialization dataWithJSONObject:changed options:0 error:nil]]);
}
- (void)testMalformedOrMismatchedRequestsDoNotReachDecoder {
    XCTAssertNil([QRWatchPhoneService.shared decodedResponseForRequestData:[@"[]" dataUsingEncoding:NSUTF8StringEncoding]]);
    NSMutableDictionary *request = [[self requestForImage:@"unicode"] mutableCopy]; request[@"sourceSHA256"] = [@"0" stringByPaddingToLength:64 withString:@"0" startingAtIndex:0];
    XCTAssertNil([QRWatchPhoneService.shared decodedResponseForRequestData:[NSJSONSerialization dataWithJSONObject:request options:0 error:nil]]);
    request[@"requestID"] = @"../not-a-uuid";
    XCTAssertNil([QRWatchPhoneService.shared decodedResponseForRequestData:[NSJSONSerialization dataWithJSONObject:request options:0 error:nil]]);
}
@end
