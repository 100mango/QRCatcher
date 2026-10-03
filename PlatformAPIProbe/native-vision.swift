import SwiftUI
import PhotosUI
import Photos
import CoreImage
import Vision
struct VisionImportProbe: View {
    @State private var selection: PhotosPickerItem?
    var body: some View { PhotosPicker(selection: $selection, matching: .images) { Text("Import photo") } }
}
func imageProbe() { _ = CIContext(); _ = VNDetectBarcodesRequest(); _ = PHPhotoLibrary.shared() }
