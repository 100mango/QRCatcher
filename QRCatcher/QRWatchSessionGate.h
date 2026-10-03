#import <Foundation/Foundation.h>
NS_ASSUME_NONNULL_BEGIN
/// Small thread-safe epoch gate. No transport, credentials or device identity.
@interface QRWatchSessionGate : NSObject
- (NSUInteger)activateCounterpart;
- (void)invalidate;
- (NSUInteger)currentTicket;
- (BOOL)performIfCurrent:(NSUInteger)ticket block:(void (^)(void))block;
@end
NS_ASSUME_NONNULL_END
