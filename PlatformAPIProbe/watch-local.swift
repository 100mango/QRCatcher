import SwiftUI
import PhotosUI
import CoreGraphics
import ImageIO
import WatchConnectivity
struct WatchImportProbe: View {
    @State private var selection: PhotosPickerItem?
    var body: some View {
        PhotosPicker(selection: $selection, matching: .images) { Text("Import photo") }
    }
}
func boundedImage(_ data: Data) -> CGImage? {
    guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
    let options: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true,
       kCGImageSourceThumbnailMaxPixelSize: 512, kCGImageSourceCreateThumbnailWithTransform: true]
    return CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary)
}
func sampleContext() -> CGContext? {
    guard let space = CGColorSpace(name: CGColorSpace.sRGB) else { return nil }
    return CGContext(data: nil, width: 1, height: 1, bitsPerComponent: 8,
        bytesPerRow: 4, space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
}
func transferAvailable() -> Bool { WCSession.isSupported() }
