#import "QRWatchPhoneService.h"
#import "QRImageCodec.h"
#import "QRWatchSessionGate.h"
#import <WatchConnectivity/WatchConnectivity.h>
#import <CommonCrypto/CommonDigest.h>
#import <fcntl.h>
#import <sys/stat.h>
#import <unistd.h>

@interface QRWatchPhoneService () <WCSessionDelegate>
@property (nonatomic, strong) dispatch_queue_t queue;
@property (nonatomic, strong) NSURL *folder;
@property (nonatomic, strong) QRWatchSessionGate *gate;
@end
@implementation QRWatchPhoneService
+ (instancetype)shared { static QRWatchPhoneService *value; static dispatch_once_t once; dispatch_once(&once, ^{ value = [QRWatchPhoneService new]; }); return value; }
- (instancetype)init {
    if ((self = [super init])) {
        _gate = [QRWatchSessionGate new];
        _queue = dispatch_queue_create("100mango.QRCatcher.watch-requests", DISPATCH_QUEUE_SERIAL);
        _folder = [[[NSFileManager.defaultManager URLsForDirectory:NSApplicationSupportDirectory inDomains:NSUserDomainMask] lastObject] URLByAppendingPathComponent:@"WatchRequests" isDirectory:YES];
    } return self;
}
- (void)activate {
    if (![WCSession isSupported]) return;
    WCSession.defaultSession.delegate = self; [WCSession.defaultSession activateSession];
}
- (NSString *)digest:(NSData *)bytes {
    unsigned char digest[CC_SHA256_DIGEST_LENGTH]; CC_SHA256(bytes.bytes, (CC_LONG)bytes.length, digest);
    NSMutableString *result = [NSMutableString string]; for (NSUInteger i = 0; i < sizeof(digest); i++) [result appendFormat:@"%02x", digest[i]]; return result;
}
- (NSData *)boundedRegularFile:(NSURL *)url limit:(NSUInteger)limit {
    int descriptor = open(url.fileSystemRepresentation, O_RDONLY | O_NOFOLLOW);
    if (descriptor < 0) return nil;
    struct stat status;
    if (fstat(descriptor, &status) != 0 || !S_ISREG(status.st_mode) || status.st_size < 0 || (unsigned long long)status.st_size > limit) { close(descriptor); return nil; }
    NSFileHandle *handle = [[NSFileHandle alloc] initWithFileDescriptor:descriptor closeOnDealloc:YES];
    NSMutableData *result = [NSMutableData data]; NSError *error;
    while (YES) {
        NSData *chunk = [handle readDataUpToLength:64 * 1024 error:&error];
        if (!chunk || error) { [handle closeAndReturnError:nil]; return nil; }
        if (chunk.length == 0) break;
        if (chunk.length > limit - result.length) { [handle closeAndReturnError:nil]; return nil; }
        [result appendData:chunk];
    }
    [handle closeAndReturnError:nil]; return result;
}
- (BOOL)validMetadata:(NSDictionary *)metadata {
    return [metadata[@"kind"] isEqual:@"qrcatcher.decode.request"] && [metadata[@"version"] isEqual:@1] &&
    [metadata[@"recordID"] isKindOfClass:NSString.class] && [[NSUUID alloc] initWithUUIDString:metadata[@"recordID"]] &&
    [metadata[@"requestID"] isKindOfClass:NSString.class] && [[NSUUID alloc] initWithUUIDString:metadata[@"requestID"]] &&
    [metadata[@"sourceSHA256"] isKindOfClass:NSString.class] && [metadata[@"sourceSHA256"] length] == 64;
}
- (void)session:(WCSession *)session didReceiveFile:(WCSessionFile *)file {
    NSDictionary *metadata = file.metadata;
    NSUInteger ticket = [self.gate currentTicket];
    if (ticket == 0 || ![self validMetadata:metadata]) return;
    // The temporary received file is only valid during this callback. Copy just
    // this bounded, validated request into the app-owned durable queue first.
    NSDictionary *properties = [file.fileURL resourceValuesForKeys:@[NSURLFileSizeKey, NSURLIsRegularFileKey, NSURLIsSymbolicLinkKey] error:nil];
    NSNumber *size = properties[NSURLFileSizeKey];
    if (![properties[NSURLIsRegularFileKey] boolValue] || [properties[NSURLIsSymbolicLinkKey] boolValue] || !size || size.unsignedIntegerValue > 8 * 1024 * 1024) return;
    NSData *bytes = [self boundedRegularFile:file.fileURL limit:8 * 1024 * 1024];
    static const unsigned char signature[] = {137,80,78,71,13,10,26,10};
    if (bytes.length < 8 || memcmp(bytes.bytes, signature, 8) != 0 || bytes.length > 8 * 1024 * 1024 || ![[self digest:bytes] isEqual:metadata[@"sourceSHA256"]]) return;
    dispatch_sync(self.queue, ^{
        NSError *error;
        if (![NSFileManager.defaultManager createDirectoryAtURL:self.folder withIntermediateDirectories:YES attributes:nil error:&error]) return;
        NSNumber *symbolic; [self.folder getResourceValue:&symbolic forKey:NSURLIsSymbolicLinkKey error:&error]; if (error || symbolic.boolValue) return;
        NSArray<NSURL *> *files = [NSFileManager.defaultManager contentsOfDirectoryAtURL:self.folder includingPropertiesForKeys:@[NSURLFileSizeKey] options:0 error:&error];
        NSUInteger total = 0; for (NSURL *url in files) { NSNumber *n; [url getResourceValue:&n forKey:NSURLFileSizeKey error:nil]; total += n.unsignedIntegerValue; }
        if (files.count >= 40 || total + bytes.length * 2 > 32 * 1024 * 1024) return; // no eviction of pending requests
        NSURL *requestURL = [self.folder URLByAppendingPathComponent:[metadata[@"requestID"] stringByAppendingString:@".request.json"]];
        NSMutableDictionary *request = [metadata mutableCopy]; request[@"source"] = [bytes base64EncodedStringWithOptions:0];
        NSData *data = [NSJSONSerialization dataWithJSONObject:request options:NSJSONWritingSortedKeys error:&error];
        if (!data) return;
        if ([NSFileManager.defaultManager fileExistsAtPath:requestURL.path]) {
            NSDictionary *existingProperties = [requestURL resourceValuesForKeys:@[NSURLFileSizeKey, NSURLIsRegularFileKey, NSURLIsSymbolicLinkKey] error:nil];
            if (![existingProperties[NSURLIsRegularFileKey] boolValue] || [existingProperties[NSURLIsSymbolicLinkKey] boolValue] || [existingProperties[NSURLFileSizeKey] unsignedIntegerValue] > 12 * 1024 * 1024) return;
            NSData *existing = [self boundedRegularFile:requestURL limit:12 * 1024 * 1024];
            if (![self requestData:existing matchesRequest:data]) return; // keep a conflicting original untouched
        } else if (![data writeToURL:requestURL options:NSDataWritingAtomic error:&error]) return;
        // A fresh explicit Watch request/retry authorizes only this epoch. Merely
        // activating a new counterpart never replays retained requests.
        dispatch_async(self.queue, ^{ [self processRequest:requestURL ticket:ticket]; });
    });
}
- (void)processRequest:(NSURL *)url ticket:(NSUInteger)ticket {
    if ([self.gate currentTicket] != ticket) return;
    NSNumber *size; [url getResourceValue:&size forKey:NSURLFileSizeKey error:nil];
    if (!size || size.unsignedIntegerValue > 12 * 1024 * 1024) return;
    NSData *raw = [self boundedRegularFile:url limit:12 * 1024 * 1024];
    NSData *encoded = raw ? [self decodedResponseForRequestData:raw] : nil;
    if (!encoded) return;
    NSDictionary *request = [NSJSONSerialization JSONObjectWithData:encoded options:0 error:nil];
    NSError *error;
    NSURL *output = [self.folder URLByAppendingPathComponent:[request[@"requestID"] stringByAppendingString:@".result.json"]];
    if (![encoded writeToURL:output options:NSDataWritingAtomic error:&error]) return;
    // Hold the epoch gate across enqueue, so deactivation cannot race a stale
    // result into a newly active counterpart. No phone-history mutation occurs.
    [self.gate performIfCurrent:ticket block:^{
        if (WCSession.defaultSession.activationState != WCSessionActivationStateActivated) return;
        BOOL queued = NO;
        for (WCSessionFileTransfer *transfer in WCSession.defaultSession.outstandingFileTransfers) if ([transfer.file.metadata[@"requestID"] isEqual:request[@"requestID"]]) queued = YES;
        if (!queued) [WCSession.defaultSession transferFile:output metadata:@{@"kind":@"qrcatcher.decode.result", @"requestID":request[@"requestID"], @"epoch":@(ticket)}];
    }];
}
- (BOOL)requestData:(NSData *)left matchesRequest:(NSData *)right {
    if (!left || !right || left.length > 12 * 1024 * 1024 || right.length > 12 * 1024 * 1024) return NO;
    NSDictionary *a = [NSJSONSerialization JSONObjectWithData:left options:0 error:nil];
    NSDictionary *b = [NSJSONSerialization JSONObjectWithData:right options:0 error:nil];
    return [a isKindOfClass:NSDictionary.class] && [b isKindOfClass:NSDictionary.class] && [a isEqual:b];
}

- (NSData *)decodedResponseForRequestData:(NSData *)raw {
    if (raw.length > 12 * 1024 * 1024) return nil;
    NSDictionary *request = [NSJSONSerialization JSONObjectWithData:raw options:0 error:nil];
    if (![request isKindOfClass:NSDictionary.class] || ![self validMetadata:request] || ![request[@"source"] isKindOfClass:NSString.class]) return nil;
    NSData *source = [[NSData alloc] initWithBase64EncodedString:request[@"source"] options:0];
    if (!source || source.length > 8 * 1024 * 1024 || ![[self digest:source] isEqual:request[@"sourceSHA256"]]) return nil;
    NSError *error;
    NSArray<NSString *> *payloads = [QRImageCodec decodeImageData:source error:&error] ?: @[];
    if (payloads.count > 32) return nil;
    for (NSString *value in payloads) if ([value lengthOfBytesUsingEncoding:NSUTF8StringEncoding] > 16384) return nil;
    NSDictionary *result = @{@"kind":@"qrcatcher.decode.result", @"version":@1, @"recordID":request[@"recordID"], @"requestID":request[@"requestID"], @"sourceSHA256":request[@"sourceSHA256"], @"payloads":payloads, @"status":error ? @"invalid_image" : (payloads.count ? @"completed" : @"no_qr")};
    NSData *encoded = [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingSortedKeys error:&error];
    return encoded.length <= 2 * 1024 * 1024 ? encoded : nil;
}
- (void)session:(WCSession *)session activationDidCompleteWithState:(WCSessionActivationState)state error:(NSError *)error {
    if (state == WCSessionActivationStateActivated && !error) [self.gate activateCounterpart];
    else [self.gate invalidate];
    // Pending files stay local. Only a new explicit request/retry can process
    // them under the current counterpart, never activation by itself.
}
- (void)session:(WCSession *)session didFinishFileTransfer:(WCSessionFileTransfer *)transfer error:(NSError *)error {
    if (error) return; // retain durable files until explicit request/retry
    NSUInteger ticket = [transfer.file.metadata[@"epoch"] unsignedIntegerValue];
    if ([self.gate currentTicket] != ticket) return;
    NSString *request = transfer.file.metadata[@"requestID"];
    if (![request isKindOfClass:NSString.class] || ![[NSUUID alloc] initWithUUIDString:request]) return;
    dispatch_async(self.queue, ^{
        [self.gate performIfCurrent:ticket block:^{
            for (NSString *suffix in @[@".request.json", @".result.json"]) [NSFileManager.defaultManager removeItemAtURL:[self.folder URLByAppendingPathComponent:[request stringByAppendingString:suffix]] error:nil];
        }];
    });
}
- (void)invalidateSession:(WCSession *)session {
    [self.gate invalidate]; // immediate, not queued behind a long image decode
    for (WCSessionFileTransfer *transfer in session.outstandingFileTransfers) if ([transfer.file.metadata[@"kind"] isEqual:@"qrcatcher.decode.result"]) [transfer cancel];
}
- (void)sessionDidBecomeInactive:(WCSession *)session { [self invalidateSession:session]; }
- (void)sessionDidDeactivate:(WCSession *)session { [self invalidateSession:session]; [session activateSession]; }
@end
