import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

/// Explicit admission covers suspended processing as well as synchronous CPU
/// decoding. Cancelled queued jobs release captured images promptly; active
/// ImageIO/CPU work retains its permit until the bounded native call returns.
actor WatchPhotoCodec {
    static let byteLimit = 8 * 1024 * 1024
    private var admitted = false
    private var waiting: [(UUID, CheckedContinuation<Void, Error>)] = []
    var waitingProcessingCount: Int { waiting.count }
    private func acquire() async throws {
        try Task.checkCancellation()
        if !admitted { admitted = true; return }
        let id = UUID()
        try await withTaskCancellationHandler(operation: {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                if Task.isCancelled { continuation.resume(throwing: CancellationError()) }
                else { waiting.append((id, continuation)) }
            }
        }, onCancel: { Task { await self.cancelQueued(id) } })
    }
    private func cancelQueued(_ id: UUID) {
        guard let index = waiting.firstIndex(where: { $0.0 == id }) else { return }
        waiting.remove(at: index).1.resume(throwing: CancellationError())
    }
    func withExclusiveProcessing<T: Sendable>(_ operation: @Sendable () async throws -> T) async throws -> T {
        try await acquire()
        defer {
            if waiting.isEmpty { admitted = false }
            else { waiting.removeFirst().1.resume() }
        }
        try Task.checkCancellation()
        return try await operation()
    }
    func prepare(_ data: Data) async throws -> Data {
        try await withExclusiveProcessing { try Self.prepareBytes(data) }
    }
    private static func prepareBytes(_ data: Data) throws -> Data {
        try Task.checkCancellation()
        guard !data.isEmpty, data.count <= Self.byteLimit,
              let source = CGImageSourceCreateWithData(data as CFData, [kCGImageSourceShouldCache: false] as CFDictionary),
              let info = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let width = info[kCGImagePropertyPixelWidth] as? NSNumber,
              let height = info[kCGImagePropertyPixelHeight] as? NSNumber else { throw WatchStoreError.invalidImage }
        let w = width.int64Value, h = height.int64Value
        guard w > 0, h > 0, w <= 16384, h <= 16384, w * h <= 40_000_000 else { throw WatchStoreError.imageLimit }
        let options: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceThumbnailMaxPixelSize: 1536,
                                       kCGImageSourceCreateThumbnailWithTransform: true, kCGImageSourceShouldCacheImmediately: true]
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else { throw WatchStoreError.invalidImage }
        try Task.checkCancellation()
        let output = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(output, UTType.png.identifier as CFString, 1, nil) else { throw WatchStoreError.invalidImage }
        CGImageDestinationAddImage(destination, image, nil)
        guard CGImageDestinationFinalize(destination), output.length <= Self.byteLimit else { throw WatchStoreError.imageLimit }
        return output as Data
    }
    func decode(_ preparedPNG: Data) async throws -> [String] {
        try await withExclusiveProcessing {
            try Task.checkCancellation()
            guard Self.validPreparedPNG(preparedPNG), let image = Self.preview(preparedPNG) else { throw WatchStoreError.invalidImage }
            let values = try QRPortableImageDecoder.decode(image)
            try Task.checkCancellation()
            return values
        }
    }
    static func validPreparedPNG(_ data: Data) -> Bool {
        guard data.count <= byteLimit,
              let source = CGImageSourceCreateWithData(data as CFData, [kCGImageSourceShouldCache: false] as CFDictionary),
              CGImageSourceGetType(source) as String? == UTType.png.identifier,
              let info = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let width = info[kCGImagePropertyPixelWidth] as? NSNumber, let height = info[kCGImagePropertyPixelHeight] as? NSNumber else { return false }
        return width.intValue > 0 && height.intValue > 0 && width.intValue <= 1536 && height.intValue <= 1536
    }
    static func preview(_ data: Data) -> CGImage? {
        // Re-check durable bytes before raster expansion, even if an archive was
        // externally damaged or replaced between releases.
        guard validPreparedPNG(data), let source = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
        return CGImageSourceCreateImageAtIndex(source, 0, nil)
    }
}
