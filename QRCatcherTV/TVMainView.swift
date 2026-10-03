import SwiftUI
import Photos
import UIKit

struct TVMainView: View {
    @ObservedObject var history: TVHistory
    @StateObject private var session: TVReadSession
    @StateObject private var library = TVPhotoLibrary()
    @State private var showPhotos = false
    @State private var showHistory = false
    @State private var showPrivacy = false
    @State private var clearHistory = false
    private enum Action: Hashable { case photos, history, privacy }
    @FocusState private var focusedAction: Action?
    init(history: TVHistory) {
        self.history = history
        _session = StateObject(wrappedValue: TVReadSession(history: history))
    }
    var code: UIImage? { session.payload.flatMap { QRImageCodec.png(payload: $0) }.flatMap { UIImage(data: $0) } }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 28) {
                    Text("QRCatcher").font(.largeTitle.bold())
                    HStack(spacing: 35) {
                        Button("Photos") { library.requestAccess(); showPhotos = true }.focused($focusedAction, equals: .photos).accessibilityIdentifier("tv.photos")
                        Button("History") { showHistory = true }.focused($focusedAction, equals: .history).accessibilityIdentifier("tv.history")
                        Button("Privacy") { showPrivacy = true }.focused($focusedAction, equals: .privacy).accessibilityIdentifier("tv.privacy")
                    }
                    if let payload = session.payload {
                        HStack(alignment: .center, spacing: 60) {
                            if let code { Image(uiImage: code).resizable().interpolation(.none).scaledToFit().frame(width: 360, height: 360).accessibilityLabel("Scannable QR representation of this result") }
                            else { Text("This result is too large to display as a QR image. Its text is still available.").frame(width: 360) }
                            VStack(alignment: .leading, spacing: 28) {
                                Text(verbatim: payload).font(.title2).accessibilityIdentifier("tv.payload")
                                if code != nil { Text("Scan this QR code with your phone. Nothing opens automatically.").foregroundStyle(.secondary) }
                                if session.decodedResults.count > 1 {
                                    Text("Code \(session.resultIndex + 1) of \(session.decodedResults.count)")
                                    HStack { Button("Previous Code") { session.changeResult(by: -1) }; Button("Next Code") { session.changeResult(by: 1) } }
                                }
                                Button(LocalizedStringKey(session.isExporting ? "Verifying Photos save…" : "Save QR to Photos")) { session.export() }.disabled(session.isExporting || code == nil).accessibilityIdentifier("tv.export")
                            }.frame(maxWidth: 760)
                        }
                    } else {
                        Image(systemName: "qrcode.viewfinder").font(.system(size: 150)).foregroundStyle(.tint)
                        Text("Read a QR image from Photos, save the result on this TV, and display a code your phone can scan.").multilineTextAlignment(.center).frame(maxWidth: 950)
                    }
                    if session.isReading { ProgressView(); Button("Cancel", action: session.cancel) }
                    Text(session.status).foregroundStyle(.secondary).accessibilityIdentifier("tv.status")
                    if let error = history.error { Text(error).foregroundStyle(.orange).multilineTextAlignment(.center).frame(maxWidth: 1050) }
                }.padding(60)
            }
            .onAppear { focusedAction = .photos }
            .sheet(isPresented: $showPhotos, onDismiss: { focusedAction = .photos }) {
                TVPhotosView(library: library) { asset in showPhotos = false; session.read(asset) }
            }
            .sheet(isPresented: $showHistory, onDismiss: { focusedAction = .history }) {
                TVHistoryView(history: history) { item in session.select(item); showHistory = false }
            }
            .sheet(isPresented: $showPrivacy, onDismiss: { focusedAction = .privacy }) { TVPrivacyView() }
            .alert("QRCatcher", isPresented: Binding(get: { session.error != nil }, set: { if !$0 { session.error = nil } })) {
                Button("OK") { session.error = nil }
            } message: { Text(session.error ?? "") }
            .onDisappear { session.cancel() }
        }
    }
}

private struct TVPhotosView: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var library: TVPhotoLibrary
    let choose: (PHAsset) -> Void
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 30) {
                    HStack { Button("Back") { dismiss() }.accessibilityIdentifier("tv.photosBack"); Button("Retry") { library.requestAccess() } }
                    Text("Photos").font(.largeTitle.bold())
                    Text(library.status).foregroundStyle(.secondary).multilineTextAlignment(.center)
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 260, maximum: 320))], spacing: 35) {
                        ForEach(Array(library.assets.enumerated()), id: \.element.localIdentifier) { index, asset in
                            Button { choose(asset) } label: { TVPhotoTile(asset: asset) }
                                .accessibilityLabel("Photo \(index + 1)").accessibilityIdentifier("tv.asset.\(index)")
                        }
                    }
                    if library.hasMore { Button("More Photos") { library.more() } }
                }.padding(65)
            }.onExitCommand { dismiss() }
        }
    }
}

private struct TVPhotoTile: View {
    let asset: PHAsset
    @State private var image: UIImage?
    @State private var request: PHImageRequestID?
    var body: some View {
        Group {
            if let image { Image(uiImage: image).resizable().scaledToFit() }
            else { Image(systemName: "photo").resizable().scaledToFit().padding(60) }
        }.frame(width: 260, height: 190)
            .onAppear {
                let options = PHImageRequestOptions(); options.isNetworkAccessAllowed = false; options.deliveryMode = .highQualityFormat
                request = PHImageManager.default().requestImage(for: asset, targetSize: CGSize(width: 520, height: 380), contentMode: .aspectFit, options: options) { image, _ in
                    Task { @MainActor in self.image = image }
                }
            }
            .onDisappear { if let request { PHImageManager.default().cancelImageRequest(request) }; request = nil }
    }
}

private struct TVHistoryView: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var history: TVHistory
    let select: (TVQRRecord) -> Void
    @State private var deleting: TVQRRecord?
    @State private var clear = false
    var body: some View {
        NavigationStack {
            List {
                Button("Back") { dismiss() }.accessibilityIdentifier("tv.historyBack")
                if history.items.isEmpty { Text(QRL(history.error == nil ? "No saved QR codes yet" : "History is unavailable")) }
                ForEach(history.items) { item in
                    // One action per focusable row: a VStack containing two
                    // buttons becomes one tvOS focused cell with no unambiguous
                    // Select action. Keep opening and removal separate.
                    Section {
                        Button { select(item) } label: {
                            VStack(alignment: .leading, spacing: 12) {
                                Text(verbatim: item.payload).lineLimit(3)
                                Text(item.createdAt, style: .date).font(.caption)
                            }.padding(.vertical, 10)
                        }.accessibilityIdentifier("tv.record")
                        // This row opens confirmation; deletion happens only in
                        // the destructive dialog below. A destructive List row
                        // renders pale pink on the focused white card on tvOS 27.
                        Button("Delete Record") { deleting = item }
                            .accessibilityIdentifier("tv.deleteRecord")
                    }
                }
                if !history.items.isEmpty || history.error != nil { Button("Clear TV History") { clear = true } }
            }.navigationTitle("History")
                .onExitCommand { dismiss() }
                .confirmationDialog("Delete this history record?", isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } })) {
                    Button("Delete Record", role: .destructive) { if let deleting { history.delete(deleting) }; deleting = nil }.accessibilityIdentifier("tv.confirmDelete")
                }
                .confirmationDialog("Clear history saved on this TV? Photos and phone history are not deleted.", isPresented: $clear) {
                    Button("Clear TV History", role: .destructive) { history.clearAfterConfirmation() }
                }
        }
    }
}

private struct TVPrivacyView: View {
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 30) {
                Text("Privacy").font(.largeTitle.bold())
                Text(QRPrivacyText.body).accessibilityIdentifier("privacy.offlineBody")
                if let data = QRImageCodec.png(payload: "https://100mango.github.io/app-privacy/"), let image = UIImage(data: data) {
                    Image(uiImage: image).resizable().interpolation(.none).scaledToFit().frame(width: 250, height: 250).accessibilityLabel("Scan to read the approved privacy policy")
                }
                Button("Done") { dismiss() }.accessibilityIdentifier("tv.privacyDone")
            }.padding(65).frame(maxWidth: 1250)
        }.onExitCommand { dismiss() }
    }
}
