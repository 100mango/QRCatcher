import Foundation
import CoreGraphics

/// Shared platform-neutral decoder plus a small CoreGraphics raster boundary.
/// Synchronous work stays within the caller's serial processing admission.
enum QRPortableImageDecoder {
    private final class Results {
        var values: [String] = []
        var invalidText = false
    }
    static func decode(_ image: CGImage) throws -> [String] {
        try Task.checkCancellation()
        let width = image.width, height = image.height
        guard width > 0, height > 0, width <= 1536, height <= 1536 else { throw failure() }
        var gray = [UInt8](repeating: 255, count: width * height)
        let collector = Results()
        let code: Int32 = gray.withUnsafeMutableBytes { buffer in
            guard let context = CGContext(data: buffer.baseAddress, width: width, height: height,
                bitsPerComponent: 8, bytesPerRow: width, space: CGColorSpaceCreateDeviceGray(),
                bitmapInfo: CGImageAlphaInfo.none.rawValue) else { return -2 }
            context.setFillColor(gray: 1, alpha: 1)
            context.fill(CGRect(x: 0, y: 0, width: CGFloat(width), height: CGFloat(height)))
            context.draw(image, in: CGRect(x: 0, y: 0, width: CGFloat(width), height: CGFloat(height)))
            return QRPortableDecodeGray(buffer.bindMemory(to: UInt8.self).baseAddress, buffer.count,
                UInt32(width), UInt32(height), { bytes, count, opaque in
                    guard let bytes, let opaque else { return 1 }
                    let values = Unmanaged<Results>.fromOpaque(opaque).takeUnretainedValue()
                    if Task.isCancelled { return 1 }
                    guard count <= 16384, values.values.count < 32,
                          let text = String(data: Data(bytes: bytes, count: count), encoding: .utf8) else {
                        values.invalidText = true; return 1
                    }
                    values.values.append(text); return 0
                }, Unmanaged.passUnretained(collector).toOpaque())
        }
        try Task.checkCancellation()
        guard code == 0, !collector.invalidText else { throw failure() }
        return collector.values
    }
    private static func failure() -> NSError {
        NSError(domain: "QRCatcher.PortableQR", code: 1,
            userInfo: [NSLocalizedDescriptionKey: NSLocalizedString("This QR photo could not be decoded. Its existing saved data was kept.", comment: "")])
    }
}
