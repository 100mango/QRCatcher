import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import Vision

/// Serial actor: only one ImageIO/Vision job can run at a time. Cancellation is
/// checked before each expensive stage and callers reject obsolete generations.
actor WatchPhotoCodec {
    static let byteLimit = 8 * 1024 * 1024
    func prepare(_ data: Data) throws -> Data {
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
    @available(watchOS 27.0, *)
    func decode(_ preparedPNG: Data) async throws -> [String] {
        try Task.checkCancellation()
        var request = DetectBarcodesRequest(); request.symbologies = [.qr]
        let observations = try await request.perform(on: preparedPNG)
        try Task.checkCancellation()
        let values = observations.compactMap { $0.payloadString }
        guard values.count <= 32, values.allSatisfy({ $0.utf8.count <= 16384 }) else { throw WatchStoreError.imageLimit }
        return values
    }
    static func preview(_ data: Data) -> CGImage? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
        return CGImageSourceCreateImageAtIndex(source, 0, nil)
    }
}
