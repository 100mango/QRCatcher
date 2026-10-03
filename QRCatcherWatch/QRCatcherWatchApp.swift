import SwiftUI
import PhotosUI
import CoreTransferable
import UniformTypeIdentifiers

@main struct QRCatcherWatchApp: App {
    var body: some Scene { WindowGroup { WatchCollectionView() } }
}
@MainActor final class WatchWorkspace: ObservableObject {
    let history = WatchHistory()
    lazy var phone = WatchPhoneTransport(history: history)
    private let codec = WatchPhotoCodec()
    private var importTask: Task<Void, Never>?
    func startRead(_ selection: PhotosPickerItem) {
        guard !importing else { return }
        importTask = Task { await read(selection) }
    }
    func cancelRead() { importTask?.cancel() }
    @Published var importing = false
    @Published var error: String?
    func read(_ selection: PhotosPickerItem) async {
        guard !importing else { return }
        importing = true; defer { importing = false }
        do {
            guard let file = try await selection.loadTransferable(type: WatchSelectedPhoto.self) else { throw WatchStoreError.invalidImage }
            let source = try await codec.prepare(file.data)
            try Task.checkCancellation()
            if #available(watchOS 27.0, *) {
                let values = try await codec.decode(source)
                guard !values.isEmpty else { throw WatchStoreError.noQR }
                try history.append(source: source, payloads: values)
            } else {
                // Older supported watches retain the actual selected photo. Only
                // the explicit request button sends it to the paired iPhone.
                try history.append(source: source, payloads: [])
            }
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
    var body: some View {
        NavigationStack {
            List {
                PhotosPicker(selection: $selection, matching: .images) { Label("Read QR Photo", systemImage: "qrcode.viewfinder") }
                    .accessibilityIdentifier("watch.photos").disabled(model.importing || history.error != nil)
                if model.importing { ProgressView("Reading photo…"); Button("Cancel") { model.cancelRead() } }
                if let error = history.error { Text(error).accessibilityIdentifier("watch.store-error") }
                if history.records.isEmpty { Text("Choose a QR photo. Saved photos and results stay available offline on this Watch.") }
                if #unavailable(watchOS 27.0) { Text("Local reading requires watchOS 27. Choose a photo, then request processing on iPhone.").font(.footnote) }
                ForEach(history.records) { record in
                    NavigationLink { WatchRecordView(model: model, history: history, phone: phone, id: record.id) } label: {
                        VStack(alignment: .leading) { Text(record.payloads.first ?? String(localized: "Photo awaiting iPhone")).lineLimit(3); Text(record.createdAt, style: .date).font(.caption2) }
                    }.accessibilityIdentifier("watch.record")
                }
                NavigationLink("Privacy Policy") {
                    ScrollView { VStack(alignment: .leading, spacing: 12) { Text(QRPrivacyText.body); Text("https://100mango.github.io/app-privacy/").font(.footnote) }.padding() }
                        .navigationTitle("Privacy Policy").accessibilityIdentifier("watch.policy")
                }.accessibilityIdentifier("watch.privacy")
            }.navigationTitle("QRCatcher")
        }.onChange(of: selection) { value in if let value { model.startRead(value) } }
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
        ScrollView {
            if let record {
                VStack(spacing: 12) {
                    if let image = WatchPhotoCodec.preview(record.sourcePNG) {
                        ScrollView([.horizontal, .vertical]) {
                            Image(image, scale: 1, label: Text("Saved QR source photo")).resizable().interpolation(.none)
                                .aspectRatio(contentMode: .fit).frame(width: 160 * zoom).accessibilityIdentifier("watch.source-image")
                        }.frame(height: 170)
                        HStack { Button("−") { zoom = max(1, zoom - 1) }.accessibilityLabel("Zoom out"); Button("+") { zoom = min(4, zoom + 1) }.accessibilityLabel("Zoom in") }
                        Text("Original selected QR photo").font(.caption2)
                    }
                    ForEach(Array(record.payloads.enumerated()), id: \.offset) { _, payload in Text(payload).accessibilityIdentifier("watch.payload") }
                    if let state = record.phoneState { Text(LocalizedStringKey(state.capitalized)).accessibilityIdentifier("watch.phone-state") }
                    if let error = record.phoneError { Text(error).font(.footnote) }
                    if record.phoneState == "pending" {
                        Text("Waiting for paired iPhone. Delivery may happen later.").font(.footnote)
                        Button("Cancel Request") { do { try phone.cancel(id) } catch { model.error = error.localizedDescription } }
                    } else {
                        Button("Read on iPhone") { do { try phone.request(id) } catch { model.error = error.localizedDescription } }.accessibilityIdentifier("watch.phone-request")
                    }
                    Text("Sends only this selected photo to your paired iPhone when you choose Read on iPhone. No link opens automatically.").font(.footnote)
                    if !phone.status.isEmpty { Text(phone.status).font(.footnote) }
                    Button("Remove from Watch", role: .destructive) { confirmDelete = true }.accessibilityIdentifier("watch.remove")
                }
            }
        }.confirmationDialog("Remove this local item?", isPresented: $confirmDelete) {
            Button("Remove from Watch", role: .destructive) { do { try phone.cancel(id); try history.remove(id); dismiss() } catch { model.error = error.localizedDescription } }
            Button("Cancel", role: .cancel) { }
        } message: { Text("Only this Watch copy is removed. Photos and iPhone history are unchanged.") }
    }
}
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
