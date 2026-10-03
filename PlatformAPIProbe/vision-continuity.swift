import AVFoundation
func continuityDeviceProbe() {
    _ = AVCaptureDevice.DiscoverySession(deviceTypes: [.continuityCamera], mediaType: .video, position: .unspecified)
}
