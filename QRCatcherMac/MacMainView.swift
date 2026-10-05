import SwiftUI
import PhotosUI
import UniformTypeIdentifiers

struct MacMainView: View {
    @ObservedObject var workspace: MacWorkspace
    @ObservedObject var history: MacHistory
    @State private var photo: PhotosPickerItem?
    @State private var sheet: Sheet?
    @State private var targeted = false
    @State private var deleteItem: HistoryItem?
    enum Sheet: String, Identifiable { case camera, privacy; var id: String { rawValue } }

    var filtered: [HistoryItem] {
        history.items.filter { workspace.search.isEmpty || $0.text.localizedCaseInsensitiveContains(workspace.search) }
    }

    var body: some View {
        NavigationSplitView {
            VStack(spacing: 0) {
                List(selection: selectionBinding) {
                    ForEach(filtered) { item in
                        HistoryRow(item: item).tag(item.id)
                            .contextMenu { Button("Delete Record", role: .destructive) { deleteItem = item } }
                    }
                }
                .accessibilityLabel("Saved QR history")
                .accessibilityIdentifier("mac.history")
                .overlay { if filtered.isEmpty { Text(QRL(history.error != nil ? "History could not be loaded" : history.items.isEmpty ? "Your QR history appears here" : "No matching results")).foregroundStyle(.secondary).padding() } }
                .searchable(text: $workspace.search, prompt: "Search history")
                Group {
                    if history.error != nil { Text("History unavailable") }
                    else { Text("\(history.items.count) saved on this Mac") }
                }.font(.body).foregroundStyle(.primary).padding()
            }
            .background(MacPaneAccessibility(label: QRL("Saved QR history"), identifier: "mac.pane.history"))
            .navigationTitle("History")
            .navigationSplitViewColumnWidth(min: 220, ideal: 280, max: 380)
        } detail: {
            VStack(spacing: 0) {
                if !history.locationChoices.isEmpty {
                    VStack(spacing: 12) {
                        Text("Choose an existing history").font(.headline)
                        Text("Both files stay in place. Future scans will be saved to the history you select.").multilineTextAlignment(.center)
                        ForEach(history.locationChoices) { choice in
                            Button(choice.title) { history.chooseLocation(choice) }
                                .accessibilityIdentifier("mac.historyChoice." + choice.id.rawValue)
                        }
                    }.padding()
                }
                QRResultView(workspace: workspace, historyError: history.error)
            }
                .background(MacPaneAccessibility(label: QRL("QR Result"), identifier: "mac.pane.result"))
                .background(targeted ? Color.accentColor.opacity(0.08) : Color.clear)
                .onDrop(of: [UTType.fileURL, UTType.image], isTargeted: $targeted, perform: workspace.dropped)
        }
        .toolbar {
            ToolbarItemGroup {
                Button(action: workspace.importFile) { Label("Open Image", systemImage: "folder") }.accessibilityIdentifier("mac.import")
                PhotosPicker(selection: $photo, matching: .images) { Label("Photos", systemImage: "photo") }.accessibilityIdentifier("mac.photos")
                Button(action: workspace.pasteImage) { Label("Paste Image", systemImage: "doc.on.clipboard") }.accessibilityIdentifier("mac.paste")
                Button { sheet = .camera } label: { Label("Camera", systemImage: "camera") }.accessibilityIdentifier("mac.camera")
                Button(action: workspace.exportHistory) { Label("Export History", systemImage: "square.and.arrow.up") }.accessibilityIdentifier("mac.exportHistory")
                Button { sheet = .privacy } label: { Label("Privacy", systemImage: "hand.raised") }.accessibilityIdentifier("mac.privacy")
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("QRCatcher workspace")
        .accessibilityIdentifier("mac.workspace")
        .task(id: photo) { await readPhoto() }
        .sheet(item: $sheet) { value in
            switch value {
            case .camera: MacCameraView(onRead: workspace.accept)
            case .privacy: MacPrivacyView()
            }
        }
        .alert("QRCatcher", isPresented: Binding(get: { workspace.error != nil }, set: { if !$0 { workspace.error = nil } })) {
            Button("OK") { workspace.error = nil }
        } message: { Text(workspace.error ?? "") }
        .confirmationDialog("Delete this history record?", isPresented: Binding(get: { deleteItem != nil }, set: { if !$0 { deleteItem = nil } })) {
            Button("Delete Record", role: .destructive) { if let deleteItem { history.delete(deleteItem) }; deleteItem = nil }
        } message: { Text("The original image is not affected.") }
    }

    private var selectionBinding: Binding<String?> {
        Binding(get: { workspace.selection }, set: { workspace.queueSelection($0) })
    }

    private func readPhoto() async {
        guard let photo else { return }
        let token = workspace.beginExternalLoad()
        do {
            let data = try await photo.loadTransferable(type: QRSelectedPhotoFile.self)?.data
            if !Task.isCancelled { workspace.completeExternalLoad(token, data: data, error: nil) }
        } catch { if !Task.isCancelled { workspace.completeExternalLoad(token, data: nil, error: error) } }
    }
}

private struct HistoryRow: View {
    let item: HistoryItem
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: item.webURL == nil ? "text.alignleft" : "globe").foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 5) {
                Text(item.text).lineLimit(2)
                if let date = item.createdAt { Text(date, style: .date).font(.caption).foregroundStyle(.secondary) }
            }
        }.padding(.vertical, 6).accessibilityElement(children: .combine)
    }
}

private struct QRResultView: View {
    @ObservedObject var workspace: MacWorkspace
    let historyError: String?
    var image: NSImage? { workspace.payload.flatMap { QRImageCodec.png(payload: $0) }.flatMap(NSImage.init(data:)) }

    var body: some View {
        ScrollView {
            VStack(spacing: 22) {
                Image(systemName: "qrcode.viewfinder").font(.system(size: 40)).foregroundStyle(Color.accentColor)
                Text(QRL(workspace.payload == nil ? "Read a QR code" : "QR Result")).font(.largeTitle.bold())
                if let payload = workspace.payload {
                    if let image {
                        Image(nsImage: image).interpolation(.none).resizable().scaledToFit().frame(width: 200, height: 200)
                            .accessibilityLabel("Scannable QR representation of the selected result")
                    }
                    Text(payload).font(.title3).textSelection(.enabled).frame(maxWidth: 600).accessibilityIdentifier("mac.payload").id(payload)
                    MacResultActions(workspace: workspace, canOpen: QRPayload.safeWebURL(payload) != nil)
                    Text("Links open only when you choose Open in Browser.").font(.body).foregroundStyle(.primary)
                } else {
                    Text("Use an image from Files, Photos or your clipboard. You can also drop an image here, or use an available camera.")
                        .foregroundStyle(.secondary).multilineTextAlignment(.center).frame(maxWidth: 400)
                    Button("Open Image…", action: workspace.importFile).buttonStyle(.borderedProminent)
                }
                if workspace.isReading { HStack { ProgressView().controlSize(.small); Button("Cancel", action: workspace.cancelRead) } }
                Text(workspace.status).foregroundStyle(.primary).multilineTextAlignment(.center).accessibilityIdentifier("mac.status")
                if let historyError { Text(historyError).foregroundStyle(.red).textSelection(.enabled).accessibilityIdentifier("mac.historyError") }
            }.padding(36).frame(maxWidth: .infinity)
        }.navigationTitle("QRCatcher")
    }
}

private struct MacResultActions: View {
    @ObservedObject var workspace: MacWorkspace
    let canOpen: Bool
    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack {
                Button("Copy", action: workspace.copy).accessibilityIdentifier("mac.copy")
                Button("Export QR Image…", action: workspace.exportQR).accessibilityIdentifier("mac.exportQR")
                if canOpen { Button("Open in Browser", action: workspace.openWebsite).accessibilityIdentifier("mac.openWebsite") }
            }.fixedSize()
            VStack(spacing: 12) {
                Button("Copy", action: workspace.copy).accessibilityIdentifier("mac.copy")
                Button("Export QR Image…", action: workspace.exportQR).accessibilityIdentifier("mac.exportQR")
                if canOpen { Button("Open in Browser", action: workspace.openWebsite).accessibilityIdentifier("mac.openWebsite") }
            }.lineLimit(nil).fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct MacPrivacyView: View {
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Privacy").font(.title.bold())
            Text(QRPrivacyText.body).accessibilityIdentifier("privacy.offlineBody")
            Link("Read the privacy policy", destination: URL(string: "https://100mango.github.io/app-privacy/")!)
            Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
        }.padding(28).frame(width: 480)
            .background(MacSheetAccessibility(label: QRL("Privacy"), identifier: "mac.sheet.privacy"))
    }
}
