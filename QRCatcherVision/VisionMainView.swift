import SwiftUI
import PhotosUI
import UniformTypeIdentifiers
import UIKit

struct VisionMainView: View {
    @Environment(\.openURL) private var openURL
    @ObservedObject var history: MacHistory
    @StateObject private var session: VisionReadSession
    @State private var search = ""
    @State private var photo: PhotosPickerItem?
    @State private var showImporter = false
    @State private var showPrivacy = false
    @State private var export: QRExportRequest?
    @State private var deleteItem: HistoryItem?
    @State private var targeted = false

    init(history: MacHistory) {
        self.history = history
        _session = StateObject(wrappedValue: VisionReadSession(history: history))
    }
    var filtered: [HistoryItem] { history.items.filter { search.isEmpty || $0.text.localizedCaseInsensitiveContains(search) } }

    var body: some View {
        NavigationSplitView {
            List(selection: selectionBinding) {
                ForEach(filtered) { item in
                    VStack(alignment: .leading, spacing: 5) {
                        Text(item.text).lineLimit(3)
                        if let date = item.createdAt { Text(date, style: .date).font(.caption).foregroundStyle(.secondary) }
                    }.tag(item.id)
                    .contextMenu { Button("Delete Record", role: .destructive) { deleteItem = item } }
                }
            }
            .searchable(text: $search, prompt: "Search history")
            .navigationTitle("History")
            .accessibilityIdentifier("vision.history")
            .overlay { if filtered.isEmpty { Text(history.error == nil ? (history.items.isEmpty ? "Your QR history appears here" : "No matching results") : "History could not be loaded").foregroundStyle(.secondary).padding() } }
        } detail: {
            VStack {
                if !history.locationChoices.isEmpty {
                    Text(history.error ?? "").foregroundStyle(.red)
                    ForEach(history.locationChoices) { choice in Button(choice.title) { history.chooseLocation(choice) } }
                }
                VisionResultView(payload: session.payload, status: session.status, error: history.error, isReading: session.isReading,
                             copy: copy, open: openWebsite, export: exportQR, cancel: session.cancel)
            }
                .onDrop(of: [UTType.fileURL, UTType.image], isTargeted: $targeted, perform: session.drop)
                .background(targeted ? Color.accentColor.opacity(0.1) : Color.clear)
                .navigationTitle("QRCatcher")
                .toolbar {
                    ToolbarItemGroup {
                        Button { showImporter = true } label: { Label("Open Image", systemImage: "folder") }.accessibilityIdentifier("vision.import")
                        PhotosPicker(selection: $photo, matching: .images) { Label("Photos", systemImage: "photo") }.accessibilityIdentifier("vision.photos")
                        Button(action: exportHistory) { Label("Export History", systemImage: "square.and.arrow.up") }.accessibilityIdentifier("vision.exportHistory").disabled(history.error != nil)
                        Button { showPrivacy = true } label: { Label("Privacy", systemImage: "hand.raised") }
                    }
                }
        }
        .frame(minWidth: 650, minHeight: 480)
        .fileImporter(isPresented: $showImporter, allowedContentTypes: [.image]) { result in
            switch result { case .success(let url): session.read(url: url); case .failure(let error): session.error = error.localizedDescription }
        }
        .fileExporter(isPresented: Binding(get: { export != nil }, set: { if !$0 { export = nil } }), document: export?.document, contentType: export?.type ?? .png, defaultFilename: export?.filename) { result in
            switch result {
            case .success(let url):
                #if DEBUG
                do { try VisionExportTestReceipt.observe(url) }
                catch { session.error = "Export readback verification failed: \(error.localizedDescription)"; return }
                #endif
                session.status = QRL("Export completed")
            case .failure(let error): session.error = error.localizedDescription
            }
        }
        .task(id: photo) { await importPhoto() }
        .onDisappear(perform: session.cancel)
        .alert("QRCatcher", isPresented: Binding(get: { session.error != nil }, set: { if !$0 { session.error = nil } })) {
            Button("OK") { session.error = nil }
        } message: { Text(session.error ?? "") }
        .confirmationDialog("Delete this history record?", isPresented: Binding(get: { deleteItem != nil }, set: { if !$0 { deleteItem = nil } })) {
            Button("Delete Record", role: .destructive) { if let deleteItem { history.delete(deleteItem) }; deleteItem = nil }
        }
        .sheet(isPresented: $showPrivacy) { VisionPrivacyView() }
    }
    private var selectionBinding: Binding<String?> {
        Binding(get: { session.selection }, set: { session.queueSelection($0) })
    }

    private func importPhoto() async {
        guard let photo else { return }
        let token = session.beginExternalLoad()
        do {
            let data = try await photo.loadTransferable(type: QRSelectedPhotoFile.self)?.data
            if !Task.isCancelled { session.completeExternalLoad(token, data: data, error: nil) }
        } catch { if !Task.isCancelled { session.completeExternalLoad(token, data: nil, error: error) } }
    }
    private func copy() { if let payload = session.payload { UIPasteboard.general.string = payload; session.status = QRL("Result copied") } }
    private func openWebsite() {
        guard let payload = session.payload, let url = QRPayload.safeWebURL(payload) else { return }
        openURL(url) { success in if !success { session.error = QRL("The system browser could not open this website.") } }
    }
    private func exportQR() {
        guard let payload = session.payload, let png = QRImageCodec.png(payload: payload) else { session.error = QRL("This result could not be exported as a QR image."); return }
        export = QRExportRequest(document: QRExportDocument(data: png), type: .png, filename: "QRCatcher")
    }
    private func exportHistory() {
        do { export = QRExportRequest(document: QRExportDocument(data: try history.exportData()), type: .json, filename: "QRCatcher History") }
        catch { session.error = error.localizedDescription }
    }
}

private struct VisionResultView: View {
    let payload: String?
    let status: String
    let error: String?
    let isReading: Bool
    let copy: () -> Void
    let open: () -> Void
    let export: () -> Void
    let cancel: () -> Void
    var code: UIImage? { payload.flatMap { QRImageCodec.png(payload: $0) }.flatMap { UIImage(data: $0) } }
    var body: some View {
        ScrollView {
            VStack(spacing: 22) {
                Image(systemName: "qrcode.viewfinder").font(.system(size: 42)).foregroundStyle(.tint)
                Text(QRL(payload == nil ? "Read a QR code" : "QR Result")).font(.largeTitle.bold())
                if let payload {
                    if let code { Image(uiImage: code).interpolation(.none).resizable().scaledToFit().frame(width: 240, height: 240).accessibilityLabel("Scannable QR representation of this result") }
                    Text(payload).font(.title3).accessibilityIdentifier("vision.payload")
                    HStack {
                        Button("Copy", action: copy).accessibilityIdentifier("vision.copy")
                        Button("Export QR Image", action: export).accessibilityIdentifier("vision.exportQR")
                        if QRPayload.safeWebURL(payload) != nil { Button("Open in Browser", action: open).accessibilityIdentifier("vision.openWebsite") }
                    }
                } else {
                    Text("Choose an image from Files or Photos, or drop one into this window. Images are decoded locally. This app does not use passthrough cameras.").multilineTextAlignment(.center).foregroundStyle(.secondary)
                }
                if isReading { HStack { ProgressView(); Button("Cancel", action: cancel) } }
                Text(status).foregroundStyle(.secondary).accessibilityIdentifier("vision.status")
                if let error { Text(error).foregroundStyle(.red) }
            }.padding(32).frame(maxWidth: 640)
        }.frame(maxWidth: .infinity)
    }
}

private struct VisionPrivacyView: View {
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("Privacy").font(.title.bold())
            Text(QRPrivacyText.body).accessibilityIdentifier("privacy.offlineBody")
            Link("Read the privacy policy", destination: URL(string: "https://100mango.github.io/app-privacy/")!)
            Button("Done") { dismiss() }
        }.padding(32).frame(width: 520)
    }
}
