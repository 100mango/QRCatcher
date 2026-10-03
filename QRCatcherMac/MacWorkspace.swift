import AppKit
import SwiftUI
import UniformTypeIdentifiers

@MainActor
final class MacWorkspace: ObservableObject {
    @Published var payload: String?
    @Published var status = QRL("Open, drop or paste an image containing a QR code.")
    @Published var isReading = false
    @Published var selection: String?
    @Published var search = ""
    @Published var error: String?
    let history: MacHistory
    private let decoder: QRDecodeWorker
    private var generation = UUID()
    private let selectionCoordinator = QRSelectionCoordinator()
    private var task: Task<Void, Never>?
    private var providerProgress: Progress?
    private var providerCancellation = QRImportCancellation()

    init(history: MacHistory, decoder: QRDecodeWorker = .shared) { self.history = history; self.decoder = decoder }

    func queueSelection(_ identifier: String?) {
        selectionCoordinator.enqueue(identifier) { [weak self] identifier in
            guard let self else { return }
            if let item = self.history.items.first(where: { $0.id == identifier }) { self.select(item) }
            else { self.selection = nil }
        }
    }
    func select(_ item: HistoryItem) {
        cancelRead()
        selection = item.id
        payload = item.payload
        status = QRL("Saved on this Mac")
    }

    func cancelRead() {
        selectionCoordinator.invalidate();
        generation = UUID()
        task?.cancel()
        task = nil
        providerCancellation.cancel(); providerCancellation = QRImportCancellation(); providerProgress?.cancel(); providerProgress = nil
        isReading = false
    }

    func beginExternalLoad() -> UUID {
        cancelRead(); isReading = true; status = QRL("Reading image…"); return generation
    }

    func completeExternalLoad(_ token: UUID, data: Data?, error: Error?) {
        guard token == generation else { return }
        if let data { read(data: data) }
        else {
            isReading = false
            self.error = QRF("Photo could not be loaded. %@", error?.localizedDescription ?? QRL("The image could not be read."))
        }
    }

    func importFile() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.image]
        panel.allowsMultipleSelection = false
        panel.prompt = QRL("Read QR Code")
        panel.message = QRL("Choose an image containing one or more QR codes.")
        guard panel.runModal() == .OK, let url = panel.url else { return }
        read(url: url)
    }

    func read(url: URL) {
        guard url.isFileURL else { error = QRL("Only local image files can be imported."); return }
        beginRead {
            let access = url.startAccessingSecurityScopedResource()
            defer { if access { url.stopAccessingSecurityScopedResource() } }
            let bytes = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
            guard bytes <= 50 * 1024 * 1024 else { throw ImageReadError.tooLarge }
            return try Data(contentsOf: url, options: .mappedIfSafe)
        }
    }

    func read(data: Data) { beginRead { data } }

    private func beginRead(load: @escaping @Sendable () throws -> Data) {
        cancelRead()
        let token = generation
        isReading = true
        status = QRL("Reading image…")
        task = Task {
            do {
                let result = try await decoder.decode(load: load)
                guard !Task.isCancelled, token == generation else { return }
                isReading = false
                guard !result.isEmpty else { status = QRL("No QR code was found. Try a clearer image with the whole code visible."); return }
                accept(result)
            } catch {
                guard !Task.isCancelled, token == generation else { return }
                isReading = false
                self.error = error.localizedDescription
                status = QRL("Image could not be read. Your previous result is still available.")
            }
        }
    }

    func accept(_ values: [String]) {
        let nonempty = values.filter { !$0.isEmpty }
        guard let first = nonempty.first else { return }
        cancelRead()
        payload = first
        var saved = true
        for value in nonempty { if !history.record(value) { saved = false } }
        selection = history.items.first(where: { $0.payload == first })?.id
        status = saved ? (nonempty.count == 1 ? QRL("QR code read and saved on this Mac") : QRF("%ld QR codes read. Select any result in History.", nonempty.count)) : QRL("QR code read. Copy or export it now; history could not be saved.")
    }

    func pasteImage() { pasteImage(from: .general) }

    func pasteImage(from pasteboard: NSPasteboard) {
        // This method is reached only by the explicit Paste Image action. Keep
        // encoded bytes intact; NSImage/TIFF re-encoding here would eagerly
        // expand an untrusted image on the main actor before the serial bounds.
        guard let type = pasteboard.availableType(from: [.png, .tiff]),
              let data = pasteboard.data(forType: type) else {
            error = QRL("The clipboard does not contain an image. Copy an image, then choose Paste Image.")
            return
        }
        guard data.count <= 50 * 1024 * 1024 else { error = ImageReadError.tooLarge.localizedDescription; return }
        read(data: data)
    }

    func copy() {
        guard let payload else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(payload, forType: .string)
        status = QRL("Result copied")
    }

    func openWebsite() {
        guard let payload, let url = QRPayload.safeWebURL(payload) else { return }
        // This is reached only by an explicit user action; no WebView or automatic navigation.
        if !NSWorkspace.shared.open(url) { error = QRL("The system browser could not open this website.") }
    }

    func exportQR() {
        guard let payload, let data = QRImageCodec.png(payload: payload) else {
            error = QRL("This payload could not be represented as a QR image."); return
        }
        save(data, type: .png, name: "QRCatcher.png")
    }

    func exportHistory() {
        do { save(try history.exportData(), type: .json, name: QRL("QRCatcher History.json")) }
        catch { self.error = error.localizedDescription }
    }

    private func save(_ data: Data, type: UTType, name: String) {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [type]
        panel.nameFieldStringValue = name
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            try data.write(to: url, options: .atomic)
            status = QRF("Exported %@", url.lastPathComponent)
        } catch { self.error = QRF("Export failed. %@", error.localizedDescription) }
    }

    func dropped(_ providers: [NSItemProvider]) -> Bool {
        guard let provider = providers.first else { return false }
        cancelRead()
        let token = generation
        if provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, failure in
                let url = (item as? URL) ?? (item as? Data).flatMap { URL(dataRepresentation: $0, relativeTo: nil) }
                Task { @MainActor in
                    guard self.generation == token else { return }
                    if let url { self.read(url: url) }
                    else { self.error = failure?.localizedDescription ?? QRL("The dropped file could not be opened.") }
                }
            }
            return true
        }
        guard provider.hasItemConformingToTypeIdentifier(UTType.image.identifier) else { return false }
        let cancellation = providerCancellation
        providerProgress = provider.loadFileRepresentation(forTypeIdentifier: UTType.image.identifier) { url, failure in
            // Consume the provider-owned temporary file before this callback
            // returns. Never first materialize arbitrary provider image Data.
            let result: Result<Data, Error>
            do {
                guard let url else { throw failure ?? CocoaError(.fileReadUnknown) }
                result = .success(try QRBoundedPhotoFile.read(url, isCancelled: { cancellation.isCancelled }))
            } catch { result = .failure(error) }
            Task { @MainActor in
                guard self.generation == token else { return }
                switch result {
                case .success(let data): self.read(data: data)
                case .failure(let error): self.error = error.localizedDescription
                }
            }
        }
        return true
    }
}

enum ImageReadError: LocalizedError {
    case tooLarge
    var errorDescription: String? { QRL("Choose an image smaller than 50 MB.") }
}
