#import "QRPayload.h"
@implementation QRPayload
+ (NSURL *)safeWebURL:(NSString *)string {
    NSString *trimmed = [string stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (trimmed.length == 0 || [trimmed rangeOfCharacterFromSet:NSCharacterSet.whitespaceAndNewlineCharacterSet].location != NSNotFound) return nil;
    NSURLComponents *parts = [NSURLComponents componentsWithString:trimmed];
    if (!parts.scheme.length) {
        // Bare web hosts remain supported; ordinary text must not become an accidental URL.
        if (![trimmed containsString:@"."]) return nil;
        parts = [NSURLComponents componentsWithString:[@"https://" stringByAppendingString:trimmed]];
    }
    NSString *scheme = parts.scheme.lowercaseString;
    if (!([scheme isEqualToString:@"http"] || [scheme isEqualToString:@"https"])) return nil;
    if (!parts.host.length || parts.user.length || parts.password.length) return nil;
    return parts.URL;
}
@end

@implementation QRHistoryValue
- (instancetype)initWithIdentifier:(NSString *)identifier payload:(NSString *)payload createdAt:(NSDate *)createdAt {
    if ((self = [super init])) { _identifier = [identifier copy]; _payload = [payload copy]; _createdAt = [createdAt copy]; }
    return self;
}
- (NSDictionary *)exportValue {
    return @{ @"payload": self.payload ?: NSNull.null, @"createdAtUnixSeconds": self.createdAt ? @(self.createdAt.timeIntervalSince1970) : NSNull.null };
}
@end
