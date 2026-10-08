import Foundation

/// Provider files are consumed while the transfer callback owns their lifetime.
/// Encoded size is checked before allocation and during each cancellable read.
enum QRBoundedPhotoFile {
    static let maximumBytes = 50 * 1024 * 1024
    static func read(_ url: URL, isCancelled: @escaping () -> Bool = { Task.isCancelled }) throws -> Data {
        try Task.checkCancellation()
        do {
            return try QRBoundedImageFileReader.read(url, isCancelled: { Task.isCancelled || isCancelled() })
        } catch let error as NSError where error.domain == NSCocoaErrorDomain && error.code == CocoaError.Code.userCancelled.rawValue {
            throw CancellationError()
        }
    }
}
/// A provider callback is not necessarily a Swift task. This token propagates
/// cancellation into its bounded file read before the temporary URL expires.
final class QRImportCancellation: @unchecked Sendable {
    private let lock = NSLock()
    private var cancelled = false
    func cancel() { lock.lock(); cancelled = true; lock.unlock() }
    var isCancelled: Bool { lock.lock(); defer { lock.unlock() }; return cancelled }
}
#if os(macOS) || os(visionOS)
import CoreTransferable
import UniformTypeIdentifiers
struct QRSelectedPhotoFile: Transferable {
    let data: Data
    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(importedContentType: .image) { received in
            Self(data: try QRBoundedPhotoFile.read(received.file))
        }
    }
}
#endif
