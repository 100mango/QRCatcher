import Foundation
import ImageIO
import CoreImage
let url = URL(fileURLWithPath: CommandLine.arguments[1])
let bytes = try Data(contentsOf: url)
guard bytes.count <= 2 * 1024 * 1024,
      let source = CGImageSourceCreateWithData(bytes as CFData, nil),
      let info = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
      let width = info[kCGImagePropertyPixelWidth] as? NSNumber,
      let height = info[kCGImagePropertyPixelHeight] as? NSNumber,
      width.intValue > 0, height.intValue > 0, width.intValue <= 4096, height.intValue <= 4096,
      let image = CGImageSourceCreateImageAtIndex(source, 0, nil),
      let detector = CIDetector(ofType: CIDetectorTypeQRCode, context: CIContext(), options: [CIDetectorAccuracy: CIDetectorAccuracyHigh]) else { fatalError("Invalid bounded exported QR image") }
let values = detector.features(in: CIImage(cgImage: image)).compactMap { ($0 as? CIQRCodeFeature)?.messageString }
guard values == ["QRCatcher 你好 🌈 123"] else { fatalError("Actual exported PNG did not decode to the imported Unicode payload") }
print("VERIFIED_SYSTEM_FILE_EXPORT_PNG", image.width, image.height, values)
