import Foundation

/// Provider files are consumed while the transfer callback owns their lifetime.
/// Encoded size is checked before allocation and during each cancellable read.
enum QRBoundedPhotoFile {
    static let maximumBytes = 50 * 1024 * 1024
    static func read(_ url: URL, isCancelled: () -> Bool = { Task.isCancelled }) throws -> Data {
        if isCancelled() { throw CancellationError() }
        try Task.checkCancellation()
        let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard values.isRegularFile == true, values.isSymbolicLink != true,
              let size = values.fileSize, size > 0, size <= maximumBytes else {
            throw NSError(domain: "QRCatcher.Image", code: 1, userInfo: [NSLocalizedDescriptionKey: NSLocalizedString("Choose an image smaller than 50 MB.", comment: "")])
        }
        let handle = try FileHandle(forReadingFrom: url); defer { try? handle.close() }
        var result = Data()
        while true {
            try Task.checkCancellation()
            if isCancelled() { throw CancellationError() }
            guard let chunk = try handle.read(upToCount: 64 * 1024), !chunk.isEmpty else { break }
            guard chunk.count <= maximumBytes - result.count else {
                throw NSError(domain: "QRCatcher.Image", code: 1, userInfo: [NSLocalizedDescriptionKey: NSLocalizedString("Choose an image smaller than 50 MB.", comment: "")])
            }
            result.append(chunk)
        }
        try Task.checkCancellation()
        return result
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
