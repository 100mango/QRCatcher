#import "QRBoundedImageFileReader.h"
#import <sys/stat.h>
#import <fcntl.h>
#import <unistd.h>
#import <errno.h>
NSUInteger const QRMaximumImportedImageBytes = 50 * 1024 * 1024;
@implementation QRBoundedImageFileReader
+ (NSData *)readURL:(NSURL *)URL isCancelled:(BOOL (^)(void))isCancelled error:(NSError **)error {
    if (error) *error = nil;
    if (isCancelled()) { if (error) *error = [NSError errorWithDomain:NSCocoaErrorDomain code:NSUserCancelledError userInfo:nil]; return nil; }
    if (!URL.isFileURL) { if (error) *error = [NSError errorWithDomain:NSCocoaErrorDomain code:NSFileReadUnsupportedSchemeError userInfo:nil]; return nil; }
    BOOL scoped = [URL startAccessingSecurityScopedResource];
    int descriptor = -1;
    @try {
        descriptor = open(URL.fileSystemRepresentation, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
        struct stat before;
        if (descriptor < 0 || fstat(descriptor, &before) != 0) {
            if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:errno userInfo:nil]; return nil;
        }
        if (!S_ISREG(before.st_mode) || before.st_size <= 0 || (uint64_t)before.st_size > QRMaximumImportedImageBytes) {
            if (error) *error = [NSError errorWithDomain:@"QRCatcher.Image" code:1 userInfo:@{NSLocalizedDescriptionKey:NSLocalizedString(@"Choose an image smaller than 50 MB.", nil)}]; return nil;
        }
        NSMutableData *result = [NSMutableData data];
        uint8_t buffer[64 * 1024];
        while (YES) {
            if (isCancelled()) { if (error) *error = [NSError errorWithDomain:NSCocoaErrorDomain code:NSUserCancelledError userInfo:nil]; return nil; }
            ssize_t count = read(descriptor, buffer, sizeof(buffer));
            if (count < 0 && errno == EINTR) continue;
            if (count < 0) { if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:errno userInfo:nil]; return nil; }
            if (count == 0) break;
            if ((NSUInteger)count > QRMaximumImportedImageBytes - result.length) {
                if (error) *error = [NSError errorWithDomain:@"QRCatcher.Image" code:1 userInfo:@{NSLocalizedDescriptionKey:NSLocalizedString(@"Choose an image smaller than 50 MB.", nil)}]; return nil;
            }
            [result appendBytes:buffer length:(NSUInteger)count];
        }
        struct stat after;
        if (fstat(descriptor, &after) != 0) { if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:errno userInfo:nil]; return nil; }
        // A changed/truncated source is not a coherent snapshot, even if its final
        // byte count is below the cap. The open descriptor also prevents a path
        // replacement from redirecting the read after the initial regular-file check.
        if (result.length != (uint64_t)before.st_size || after.st_size != before.st_size ||
            after.st_mtimespec.tv_sec != before.st_mtimespec.tv_sec || after.st_mtimespec.tv_nsec != before.st_mtimespec.tv_nsec ||
            after.st_ctimespec.tv_sec != before.st_ctimespec.tv_sec || after.st_ctimespec.tv_nsec != before.st_ctimespec.tv_nsec) {
            if (error) *error = [NSError errorWithDomain:NSCocoaErrorDomain code:NSFileReadCorruptFileError userInfo:nil]; return nil;
        }
        if (isCancelled()) { if (error) *error = [NSError errorWithDomain:NSCocoaErrorDomain code:NSUserCancelledError userInfo:nil]; return nil; }
        return result;
    } @finally {
        if (descriptor >= 0) close(descriptor);
        if (scoped) [URL stopAccessingSecurityScopedResource];
    }
}
@end
