#import "QRWatchSessionGate.h"
@interface QRWatchSessionGate ()
@property (nonatomic) NSLock *lock;
@property (nonatomic) NSUInteger epoch;
@property (nonatomic) BOOL active;
@end
@implementation QRWatchSessionGate
- (instancetype)init { if ((self = [super init])) { _lock = [NSLock new]; _epoch = 1; } return self; }
- (NSUInteger)activateCounterpart { [self.lock lock]; self.epoch++; self.active = YES; NSUInteger ticket = self.epoch; [self.lock unlock]; return ticket; }
- (void)invalidate { [self.lock lock]; self.epoch++; self.active = NO; [self.lock unlock]; }
- (NSUInteger)currentTicket { [self.lock lock]; NSUInteger result = self.active ? self.epoch : 0; [self.lock unlock]; return result; }
- (BOOL)performIfCurrent:(NSUInteger)ticket block:(void (^)(void))block {
    [self.lock lock]; BOOL allowed = ticket != 0 && self.active && ticket == self.epoch;
    if (allowed) block(); [self.lock unlock]; return allowed;
}
@end
