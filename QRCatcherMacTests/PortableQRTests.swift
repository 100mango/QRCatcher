import XCTest
import ImageIO
import CoreGraphics
@testable import QRCatcherMac

final class PortableQRTests: XCTestCase {
    func testActualCoreGraphicsPortableDecodeAndExistingCodecEquivalence() throws {
        let goldens: [(String, [String])] = [
            ("ascii", ["https://example.com/qrcatcher?source=golden"]),
            ("unicode", ["QRCatcher 你好 🌈 123"]), ("rotated", ["QRCatcher 你好 🌈 123"]),
            ("multiple", ["https://example.com/qrcatcher?source=golden", "QRCatcher 你好 🌈 123"]), ("invalid", []),
            ("eci-utf8", ["你好 🌈"]), ("eci-latin1", ["Café"]), ("eci-shiftjis", ["日本語"]), ("eci-mixed", ["Café 你好"])
        ]
        for (name, expected) in goldens {
            let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: name, withExtension: "png"))
            let data = try Data(contentsOf: url)
            let source = try XCTUnwrap(CGImageSourceCreateWithData(data as CFData, nil))
            let image = try XCTUnwrap(CGImageSourceCreateImageAtIndex(source, 0, nil))
            let actual = try QRPortableImageDecoder.decode(image)
            XCTAssertEqual(Set(actual), Set(expected), name); XCTAssertEqual(actual.count, expected.count, name)
            if ["ascii", "unicode", "rotated", "multiple", "invalid"].contains(name) {
                XCTAssertEqual(Set(actual), Set(try QRImageCodec.decode(data: data)), name)
            }
        }
    }
    func testProductionPortableBoundaryRejectsTruncatedAndHugeDimensions() {
        let byte: [UInt8] = [0]
        for (width, height) in [(0,1),(100,100),(1537,1),(Int(UInt32.max),Int(UInt32.max))] {
            let result = byte.withUnsafeBufferPointer { pixels in
                QRPortableDecodeGray(pixels.baseAddress, pixels.count, UInt32(width), UInt32(height), { _, _, _ in XCTFail("Invalid input must never produce a payload"); return 0 }, nil)
            }
            XCTAssertEqual(result, -1)
        }
    }
    func testProductionCallbackCancellationStopsPayloadDelivery() throws {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "multiple", withExtension: "png"))
        let source = try XCTUnwrap(CGImageSourceCreateWithURL(url as CFURL, nil))
        let image = try XCTUnwrap(CGImageSourceCreateImageAtIndex(source, 0, nil))
        var gray = [UInt8](repeating: 255, count: image.width * image.height)
        let calls = UnsafeMutablePointer<Int32>.allocate(capacity: 1)
        calls.initialize(to: 0); defer { calls.deinitialize(count: 1); calls.deallocate() }
        let result = try gray.withUnsafeMutableBytes { buffer -> Int32 in
            let context = try XCTUnwrap(CGContext(data: buffer.baseAddress, width: image.width, height: image.height,
                bitsPerComponent: 8, bytesPerRow: image.width, space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGImageAlphaInfo.none.rawValue))
            context.draw(image, in: CGRect(x: 0, y: 0, width: CGFloat(image.width), height: CGFloat(image.height)))
            return QRPortableDecodeGray(buffer.bindMemory(to: UInt8.self).baseAddress, buffer.count,
                UInt32(image.width), UInt32(image.height), { _, _, opaque in
                    opaque!.assumingMemoryBound(to: Int32.self).pointee += 1
                    return 1
                }, calls)
        }
        XCTAssertEqual(result, -4); XCTAssertEqual(calls.pointee, 1)
    }
}
