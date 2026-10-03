import SwiftUI
import AVFoundation
import AVKit
struct TVCameraProbe: View {
    @State private var presented = false
    var body: some View {
        Text("Camera").continuityDevicePicker(isPresented: $presented, onDidConnect: { _ in })
    }
}
func cameraProbe() {
    _ = AVContinuityDevicePickerViewController.isSupported
    _ = AVCaptureDevice.DiscoverySession(deviceTypes: [.continuityCamera], mediaType: .video, position: .unspecified)
    let session = AVCaptureSession()
    _ = session.canAddOutput(AVCaptureVideoDataOutput())
}
