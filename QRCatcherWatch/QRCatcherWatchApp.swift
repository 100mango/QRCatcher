import SwiftUI
import PhotosUI
import CoreTransferable
import UniformTypeIdentifiers

@main struct QRCatcherWatchApp: App {
    var body: some Scene {
        WindowGroup {
            #if DEBUG
            if ProcessInfo.processInfo.environment["QRCATCHER_WATCH_LAYOUT_STRESS"] == "accessibility5" {
                WatchCollectionView().dynamicTypeSize(.accessibility5)
            } else { WatchCollectionView() }
            #else
            WatchCollectionView()
            #endif
        }
    }
}
@MainActor final class WatchWorkspace: ObservableObject {
    let history = WatchHistory()
    lazy var phone = WatchPhoneTransport(history: history)
    private let codec = WatchPhotoCodec()
    private var importTask: Task<Void, Never>?
    func startRead(_ selection: PhotosPickerItem) {
        guard !importing else { return }
        importing = true
        importTask = Task { await read(selection) }
    }
    func cancelRead() { importTask?.cancel() }
    @Published var importing = false
    @Published var error: String?
    private func read(_ selection: PhotosPickerItem) async {
        defer { importing = false }
        do {
            guard let file = try await selection.loadTransferable(type: WatchSelectedPhoto.self) else { throw WatchStoreError.invalidImage }
            let source = try await codec.prepare(file.data)
            try Task.checkCancellation()
            let values = try await codec.decode(source)
            try Task.checkCancellation()
            // Save the bounded preview even if no QR was found, so the person
            // can choose an explicit phone retry without selecting it again.
            try history.append(source: source, payloads: values)
            if values.isEmpty { self.error = WatchStoreError.noQR.localizedDescription }
            objectWillChange.send()
        } catch is CancellationError { }
        catch { self.error = error.localizedDescription }
    }
}
struct WatchCollectionView: View {
    @StateObject private var model = WatchWorkspace()
    @State private var selection: PhotosPickerItem?
    var body: some View {
        WatchCollectionContent(model: model, history: model.history, phone: model.phone, selection: $selection)
            .alert("QRCatcher", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) {
                Button("OK", role: .cancel) { model.error = nil }
            } message: { Text(model.error ?? "") }
    }
}
private struct WatchCollectionContent: View {
    @ObservedObject var model: WatchWorkspace
    @ObservedObject var history: WatchHistory
    @ObservedObject var phone: WatchPhoneTransport
    @Binding var selection: PhotosPickerItem?
    private static var thirdPartyNotices: String {
        guard let file = Bundle.main.url(forResource: "ThirdPartyNotices", withExtension: "txt"),
              let text = try? String(contentsOf: file, encoding: .utf8) else { return "ZXing-C++: Apache License 2.0" }
        return text
    }
    var body: some View {
        NavigationStack {
            List {
                PhotosPicker(selection: $selection, matching: .images) { Label("Read QR Photo", systemImage: "qrcode.viewfinder") }
                    .accessibilityIdentifier("watch.photos").disabled(model.importing || history.error != nil)
                if model.importing { ProgressView("Reading photo…"); Button("Cancel") { model.cancelRead() } }
                if let error = history.error { Text(error).accessibilityIdentifier("watch.store-error") }
                if history.records.isEmpty { Text("Choose a QR photo. Saved photos and results stay available offline on this Watch.") }
                ForEach(history.records) { record in
                    NavigationLink { WatchRecordView(model: model, history: history, phone: phone, id: record.id) } label: {
                        VStack(alignment: .leading) { Text(record.payloads.first ?? (record.phoneState == "pending" ? String(localized: "Photo awaiting iPhone") : String(localized: "Saved QR photo"))).lineLimit(3); Text(record.createdAt, style: .date).font(.caption2) }
                    }.accessibilityIdentifier("watch.record")
                }
                NavigationLink("Privacy Policy") {
                    ScrollView { VStack(alignment: .leading, spacing: 12) { Text(QRPrivacyText.body); Text("https://100mango.github.io/app-privacy/").font(.footnote) }.padding() }
                        .navigationTitle("Privacy Policy").accessibilityIdentifier("watch.policy")
                }.accessibilityIdentifier("watch.privacy")
                NavigationLink("Licenses") {
                    ScrollView { Text(Self.thirdPartyNotices).font(.footnote).padding() }.navigationTitle("Licenses")
                }
            }.navigationTitle("QRCatcher")
        }.onChange(of: selection) { value in if let value { model.startRead(value) } }
    }
}
enum WatchPreviewLayout {
    static func side(width: CGFloat, height: CGFloat) -> CGFloat {
        max(64, min(160, width - 16, height - 24))
    }
}
private struct WatchRecordView: View {
    @ObservedObject var model: WatchWorkspace
    @ObservedObject var history: WatchHistory
    @ObservedObject var phone: WatchPhoneTransport
    let id: UUID
    @State private var confirmDelete = false
    @State private var zoom = 1.0
    @Environment(\.dismiss) private var dismiss
    private var record: WatchRecord? { history.records.first { $0.id == id } }
    var body: some View {
        GeometryReader { geometry in
            let previewSide = WatchPreviewLayout.side(width: geometry.size.width, height: geometry.size.height)
            ScrollView {
                if let record {
                    VStack(spacing: 12) {
                        if let image = WatchPhotoCodec.preview(record.sourcePNG) {
                            ScrollView([.horizontal, .vertical]) {
                                Image(image, scale: 1, label: Text("Saved QR photo preview")).resizable().interpolation(.none)
                                    .aspectRatio(contentMode: .fit).frame(width: previewSide * CGFloat(zoom), height: previewSide * CGFloat(zoom)).accessibilityIdentifier("watch.source-image")
                            }.frame(height: previewSide + 8)
                            HStack { Button("−") { zoom = max(1, zoom - 1) }.accessibilityLabel("Zoom out"); Button("+") { zoom = min(4, zoom + 1) }.accessibilityLabel("Zoom in") }
                            Text("Saved QR photo preview, up to 1536 pixels").font(.caption2)
                        } else { Text("The saved preview could not be read. Your text result is still available.").font(.footnote) }
                        ForEach(Array(record.payloads.enumerated()), id: \.offset) { _, payload in
                            #if DEBUG
                            Text(payload).modifier(WatchTraitReadback()).accessibilityIdentifier("watch.payload")
                            #else
                            Text(payload).accessibilityIdentifier("watch.payload")
                            #endif
                        }
                        if let state = record.phoneState { Text(LocalizedStringKey(state.capitalized)).accessibilityIdentifier("watch.phone-state") }
                        if let error = record.phoneError { Text(error).font(.footnote) }
                        if record.phoneState == "pending" {
                            Text("Waiting for paired iPhone. Delivery may happen later.").font(.footnote)
                            Button("Cancel Request") { do { try phone.cancel(id) } catch { model.error = error.localizedDescription } }
                        } else {
                            Button("Read on iPhone") { do { try phone.request(id) } catch { model.error = error.localizedDescription } }.accessibilityIdentifier("watch.phone-request")
                        }
                        Text("Read on iPhone sends this saved photo preview to your paired iPhone. The original Photos asset stays unchanged. No link opens automatically.").font(.footnote)
                        if !phone.status.isEmpty { Text(phone.status).font(.footnote) }
                        Button("Remove from Watch", role: .destructive) { confirmDelete = true }.accessibilityIdentifier("watch.remove")
                    }
                }
            }
        }.confirmationDialog("Remove this local item?", isPresented: $confirmDelete) {
            Button("Remove from Watch", role: .destructive) { do { try phone.cancel(id); try history.remove(id); dismiss() } catch { model.error = error.localizedDescription } }
            Button("Cancel", role: .cancel) { }
        } message: { Text("Only this Watch copy is removed. Photos and iPhone history are unchanged.") }
    }
}
#if DEBUG
/// Only the explicit layout-stress test requests this observation. It reports
/// the rendered view's public environment and scaled body metric; it does not
/// change font, frame, persistence, payload, or system preferences.
private struct WatchTraitReadback: ViewModifier {
    @Environment(\.dynamicTypeSize) private var size
    @ScaledMetric(relativeTo: .body) private var bodyMetric = 17.0
    func body(content: Content) -> some View {
        if ProcessInfo.processInfo.environment["QRCATCHER_WATCH_LAYOUT_PROBE"] == "1" {
            content.accessibilityValue("trait=\(size == .accessibility5 ? "accessibility5" : "baseline");bodyMetric=\(bodyMetric)")
        } else { content }
    }
}
#endif
private struct WatchSelectedPhoto: Transferable {
    let data: Data
    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(importedContentType: .image) { received in
            let info = try received.file.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
            guard info.isRegularFile == true, info.isSymbolicLink != true, let size = info.fileSize, size > 0, size <= WatchPhotoCodec.byteLimit else { throw WatchStoreError.imageLimit }
            let handle = try FileHandle(forReadingFrom: received.file); defer { try? handle.close() }
            var bytes = Data()
            while let chunk = try handle.read(upToCount: 64 * 1024), !chunk.isEmpty {
                try Task.checkCancellation()
                guard bytes.count + chunk.count <= WatchPhotoCodec.byteLimit else { throw WatchStoreError.imageLimit }
                bytes.append(chunk)
            }
            return Self(data: bytes)
        }
    }
}
