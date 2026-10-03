import Foundation
import Photos
import CoreImage
func photoImportProbe() -> PHFetchResult<PHAsset> { PHAsset.fetchAssets(with: .image, options: nil) }
func photoWriteProbe(_ data: Data) {
    PHPhotoLibrary.requestAuthorization(for: .readWrite) { _ in }
    PHPhotoLibrary.shared().performChanges({
        let request = PHAssetCreationRequest.forAsset()
        request.addResource(with: .photo, data: data, options: nil)
    }, completionHandler: { _, _ in })
}
func photoEditProbe(_ asset: PHAsset, output: PHContentEditingOutput) {
    guard asset.canPerform(.content) else { return }
    PHPhotoLibrary.shared().performChanges({
        PHAssetChangeRequest(for: asset).contentEditingOutput = output
    }, completionHandler: { _, _ in })
}
func coreImageProbe() { _ = CIContext(); _ = CIFilter(name: "CIQRCodeGenerator") }
