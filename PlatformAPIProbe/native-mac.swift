import SwiftUI
import AppKit
import PhotosUI
import Photos
import CoreImage
import Vision
struct MacImportProbe: View {
    @State private var selection: PhotosPickerItem?
    var body: some View { PhotosPicker(selection: $selection, matching: .images) { Text("Import photo") } }
}
func desktopProbe(_ controller: any PHContentEditingController) {
    _ = NSOpenPanel(); _ = NSSavePanel(); _ = NSPasteboard.general
    _ = CIContext(); _ = VNDetectBarcodesRequest(); _ = controller.shouldShowCancelConfirmation
}
