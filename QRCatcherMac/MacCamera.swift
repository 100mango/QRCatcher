import SwiftUI
import AVFoundation
import CoreImage

/// Actual video frames use the same QR decoder as imported images. No simulator substitution.
final class MacCamera: NSObject, ObservableObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    @Published private(set) var status = QRL("Choose Start Camera when you are ready.")
    @Published private(set) var devices = MacCamera.discoverDevices()
    @Published private(set) var running = false
    let session = AVCaptureSession()
    var onRead: (([String]) -> Void)?
    private let queue = DispatchQueue(label: "QRCatcher.camera", qos: .userInitiated)
    private var generation = 0
    private var lastFrame = CMTime.zero
    private var observers: [NSObjectProtocol] = []
    private var acceptsFrames = false
    // deliveryID belongs to the main queue; activeDeliveryID belongs to the capture queue.
    // A queued frame must never outlive a stop, source change, dismissal or interruption.
    private var deliveryID = UUID()
    private var activeDeliveryID = UUID()

    private static func discoverDevices() -> [AVCaptureDevice] {
        let types: [AVCaptureDevice.DeviceType]
        if #available(macOS 14.0, *) { types = [.builtInWideAngleCamera, .external, .continuityCamera] }
        else { types = [.builtInWideAngleCamera, .externalUnknown] }
        return AVCaptureDevice.DiscoverySession(deviceTypes: types, mediaType: .video, position: .unspecified).devices
    }

    override init() {
        super.init()
        for name in [AVCaptureDevice.wasConnectedNotification, AVCaptureDevice.wasDisconnectedNotification] {
            observers.append(NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                guard let self else { return }
                self.devices = Self.discoverDevices()
                self.stop(message: QRL("Camera connection changed. Choose a camera and start again."))
            })
        }
        for name in [AVCaptureSession.runtimeErrorNotification, AVCaptureSession.wasInterruptedNotification, NSApplication.didResignActiveNotification] {
            observers.append(NotificationCenter.default.addObserver(forName: name, object: name == NSApplication.didResignActiveNotification ? nil : session, queue: .main) { [weak self] _ in
                self?.stop(message: QRL("Camera paused or interrupted. Choose Start Camera to retry."))
            })
        }
    }

    deinit { for observer in observers { NotificationCenter.default.removeObserver(observer) } }

    func start(deviceID: String?) {
        guard let device = devices.first(where: { $0.uniqueID == deviceID }) ?? devices.first else {
            status = QRL("No camera is available. Connect a camera, or import an image instead.")
            return
        }
        deliveryID = UUID()
        let delivery = deliveryID
        status = QRL("Preparing camera…")
        queue.async {
            self.generation += 1
            let token = self.generation
            switch AVCaptureDevice.authorizationStatus(for: .video) {
            case .authorized: self.configure(device: device, token: token, delivery: delivery)
            case .notDetermined:
                AVCaptureDevice.requestAccess(for: .video) { granted in
                    self.queue.async {
                        guard token == self.generation else { return }
                        if granted { self.configure(device: device, token: token, delivery: delivery) }
                        else { self.publish(QRL("Camera access was denied. You can enable it in System Settings > Privacy & Security > Camera, or import an image."), running: false) }
                    }
                }
            default: self.publish(QRL("Camera access is unavailable. Check System Settings > Privacy & Security > Camera, or import an image."), running: false)
            }
        }
    }

    func stop(message: String = QRL("Camera stopped")) {
        deliveryID = UUID()
        queue.async {
            self.generation += 1
            self.acceptsFrames = false
            if self.session.isRunning { self.session.stopRunning() }
            self.publish(message, running: false)
        }
    }

    private func configure(device: AVCaptureDevice, token: Int, delivery: UUID) {
        guard token == generation else { return }
        if session.isRunning { session.stopRunning() }
        session.beginConfiguration()
        for input in session.inputs { session.removeInput(input) }
        for output in session.outputs { session.removeOutput(output) }
        do {
            let input = try AVCaptureDeviceInput(device: device)
            let output = AVCaptureVideoDataOutput()
            output.alwaysDiscardsLateVideoFrames = true
            output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA]
            guard session.canAddInput(input), session.canAddOutput(output) else {
                session.commitConfiguration()
                publish(QRL("This camera cannot provide video frames. Try another camera or import an image."), running: false)
                return
            }
            session.addInput(input); session.addOutput(output)
            if session.canSetSessionPreset(.high) { session.sessionPreset = .high }
            output.setSampleBufferDelegate(self, queue: queue)
            session.commitConfiguration()
            activeDeliveryID = delivery
            acceptsFrames = true; lastFrame = .zero
            session.startRunning()
            publish(QRL("Point the camera at a QR code. Nothing opens automatically."), running: session.isRunning)
        } catch {
            session.commitConfiguration()
            publish(QRF("Camera could not start: %@", error.localizedDescription), running: false)
        }
    }

    private func publish(_ text: String, running: Bool) {
        DispatchQueue.main.async { self.status = text; self.running = running }
    }

    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard acceptsFrames else { return }
        let time = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        guard CMTimeGetSeconds(CMTimeSubtract(time, lastFrame)) >= 0.3,
              let buffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        lastFrame = time
        let image = CIImage(cvPixelBuffer: buffer)
        let scale = min(1, 1920 / max(image.extent.width, image.extent.height))
        let bounded = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        let values = QRImageCodec.payloads(in: bounded)
        guard !values.isEmpty else { return }
        acceptsFrames = false
        let token = generation
        let delivery = activeDeliveryID
        // Never call stopRunning synchronously from within the output callback.
        queue.async {
            guard token == self.generation else { return }
            self.session.stopRunning()
            DispatchQueue.main.async {
                guard self.deliveryID == delivery else { return }
                self.running = false; self.onRead?(values)
            }
        }
    }
}

struct MacCameraView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var camera = MacCamera()
    @State private var deviceID: String?
    let onRead: ([String]) -> Void

    var body: some View {
        VStack(spacing: 18) {
            Text("Camera").font(.title.bold())
            CameraPreview(session: camera.session).frame(width: 560, height: 320).background(.black).clipShape(RoundedRectangle(cornerRadius: 12))
                .accessibilityLabel("Live camera preview")
            Picker("Camera", selection: $deviceID) {
                Text("Default camera").tag(String?.none)
                ForEach(camera.devices, id: \.uniqueID) { Text($0.localizedName).tag(Optional($0.uniqueID)) }
            }.disabled(camera.running || camera.devices.isEmpty)
                .accessibilityIdentifier("mac.cameraDevice")
            Text(camera.status).multilineTextAlignment(.center).accessibilityIdentifier("mac.cameraStatus")
            HStack {
                Button("Start Camera") { camera.start(deviceID: deviceID) }.disabled(camera.running).accessibilityIdentifier("mac.cameraStart")
                Button("Stop Camera") { camera.stop() }.disabled(!camera.running)
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
        }.padding(24).frame(width: 620)
        .background(MacSheetAccessibility(label: QRL("Camera"), identifier: "mac.sheet.camera"))
        .onAppear { camera.onRead = { values in onRead(values); dismiss() } }
        .onDisappear { camera.onRead = nil; camera.stop() }
    }
}

private struct CameraPreview: NSViewRepresentable {
    let session: AVCaptureSession
    func makeNSView(context: Context) -> PreviewView { PreviewView(session: session) }
    func updateNSView(_ view: PreviewView, context: Context) {}
    final class PreviewView: NSView {
        let preview: AVCaptureVideoPreviewLayer
        init(session: AVCaptureSession) {
            preview = AVCaptureVideoPreviewLayer(session: session)
            super.init(frame: .zero)
            wantsLayer = true
            preview.videoGravity = .resizeAspect
            layer?.addSublayer(preview)
        }
        required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
        override func layout() { super.layout(); preview.frame = bounds }
    }
}
