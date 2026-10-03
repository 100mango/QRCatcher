import Foundation
import CoreGraphics
import ImageIO
import CryptoKit

// Verify the actual compiled bundle icon, without assuming iconutil's filenames.
let input = URL(fileURLWithPath: CommandLine.arguments[1])
let output = URL(fileURLWithPath: CommandLine.arguments[2])
let bytes = try Data(contentsOf: input)
guard bytes.starts(with: Data("icns".utf8)),
      let source = CGImageSourceCreateWithURL(input as CFURL, nil) else { fatalError("Compiled icon is not a readable ICNS image") }
var images: [CGImage] = []
for index in 0..<CGImageSourceGetCount(source) {
    if let image = CGImageSourceCreateImageAtIndex(source, index, nil) { images.append(image) }
}
guard let image = images.max(by: { $0.width * $0.height < $1.width * $1.height }), image.width >= 512, image.height >= 512 else {
    fatalError("Compiled icon has no usable large representation")
}
try FileManager.default.createDirectory(at: output.deletingLastPathComponent(), withIntermediateDirectories: true)
guard let destination = CGImageDestinationCreateWithURL(output as CFURL, "public.png" as CFString, 1, nil) else { fatalError("Cannot export icon evidence") }
CGImageDestinationAddImage(destination, image, nil)
guard CGImageDestinationFinalize(destination) else { fatalError("Cannot finalize icon evidence") }
let report: [String: Any] = ["icns_sha256": SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined(),
                           "decoded_sizes": images.map { [$0.width, $0.height] }, "largest_size": [image.width, image.height]]
let reportData = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
try reportData.write(to: output.deletingPathExtension().appendingPathExtension("json"))
print(String(decoding: reportData, as: UTF8.self))
