import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import CryptoKit

// Archive-only TV projection of the unchanged native icon recipe.
// Only existing TV files are materialized; checked-in Top Shelf 2x PNGs are not rewritten.
let root = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
let sourceURL = root.appendingPathComponent("QRCatcher/Images.xcassets/AppIcon.appiconset/marketing1024.png")
let bytes = try Data(contentsOf: sourceURL)
let hash = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
precondition(hash == "dc2c12171d08a7d5cc51a66dc212601deccca7ab0d8d6d3c315d0da2ffa403d4")
let source = CGImageSourceCreateWithData(bytes as CFData, nil)!
let image = CGImageSourceCreateImageAtIndex(source, 0, nil)!
precondition(image.width == 1024 && image.height == 1024)
func render(_ relative: String, width: Int, height: Int, artwork: Bool, opaque: Bool) throws {
    let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
                            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    if opaque { context.setFillColor(CGColor(gray: 0.08, alpha: 1)); context.fill(CGRect(x: 0, y: 0, width: CGFloat(width), height: CGFloat(height))) }
    if artwork {
        let side = min(width, height)
        context.interpolationQuality = .high
        context.draw(image, in: CGRect(x: CGFloat(width-side)/2, y: CGFloat(height-side)/2, width: CGFloat(side), height: CGFloat(side)))
    }
    let path = root.appendingPathComponent(relative)
    let destination = CGImageDestinationCreateWithURL(path as CFURL, UTType.png.identifier as CFString, 1, nil)!
    CGImageDestinationAddImage(destination, context.makeImage()!, nil); precondition(CGImageDestinationFinalize(destination))
    let data = try Data(contentsOf: path)
    print("NATIVE_ICON", relative, width, height, SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined())
}
let tv = "QRCatcherTV/Assets.xcassets/AppIcon.brandassets/"
for (name,w,h,scale) in [("Small",400,240,"1x"),("Small",800,480,"2x"),("Large",1280,768,"1x")] {
    for layer in ["Front","Back"] { try render(tv + "\(name).imagestack/\(layer).imagestacklayer/Content.imageset/Icon-\(scale).png", width: w, height: h, artwork: layer == "Back", opaque: layer == "Back") }
}
for (name,w,h) in [("TopShelf",1920,720),("TopShelfWide",2320,720)] { try render(tv + "\(name).imageset/Icon.png", width: w, height: h, artwork: true, opaque: true) }
