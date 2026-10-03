import AppKit
import SwiftUI
import UniformTypeIdentifiers

@MainActor
final class MacWorkspace: ObservableObject {
    @Published var payload: String?
    @Published var status = "Open, drop or paste an image containing a QR code."
    @Published var isReading = false
    @Published var selection: String?
    @Published var search = ""
    @Published var error: String?
    let history: MacHistory
    private var generation = UUID()
    private var task: Task<Void, Never>?

    init(history: MacHistory) { self.history = history }

    func select(_ item: HistoryItem) {
        cancelRead()
        selection = item.id
        payload = item.payload
        status = "Saved on this Mac"
    }

    func cancelRead() {
        generation = UUID()
        task?.cancel()
        task = nil
        isReading = false
    }

    func importFile() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.image]
        panel.allowsMultipleSelection = false
        panel.prompt = "Read QR Code"
        panel.message = "Choose an image containing one or more QR codes."
        guard panel.runModal() == .OK, let url = panel.url else { return }
        read(url: url)
    }

    func read(url: URL) {
        guard url.isFileURL else { error = "Only local image files can be imported."; return }
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
        status = "Reading image…"
        task = Task {
            do {
                let result = try await Task.detached(priority: .userInitiated) {
                    try Task.checkCancellation()
                    return try QRImageCodec.decode(data: load())
                }.value
                guard !Task.isCancelled, token == generation else { return }
                isReading = false
                guard !result.isEmpty else { status = "No QR code was found. Try a clearer image with the whole code visible."; return }
                accept(result)
            } catch {
                guard !Task.isCancelled, token == generation else { return }
                isReading = false
                self.error = error.localizedDescription
                status = "Image could not be read. Your previous result is still available."
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
        status = saved ? (nonempty.count == 1 ? "QR code read and saved on this Mac" : "\(nonempty.count) QR codes read. Select any result in History.") : "QR code read. Copy or export it now; history could not be saved."
    }

    func pasteImage() {
        guard let image = NSImage(pasteboard: .general), let data = image.tiffRepresentation else {
            error = "The clipboard does not contain an image. Copy an image, then choose Paste Image."
            return
        }
        read(data: data)
    }

    func copy() {
        guard let payload else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(payload, forType: .string)
        status = "Result copied"
    }

    func openWebsite() {
        guard let payload, let url = QRPayload.safeWebURL(payload) else { return }
        // This is reached only by an explicit user action; no WebView or automatic navigation.
        if !NSWorkspace.shared.open(url) { error = "The system browser could not open this website." }
    }

    func exportQR() {
        guard let payload, let data = QRImageCodec.png(payload: payload) else {
            error = "This payload could not be represented as a QR image."; return
        }
        save(data, type: .png, name: "QRCatcher.png")
    }

    func exportHistory() {
        do { save(try history.exportData(), type: .json, name: "QRCatcher History.json") }
        catch { self.error = error.localizedDescription }
    }

    private func save(_ data: Data, type: UTType, name: String) {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [type]
        panel.nameFieldStringValue = name
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            try data.write(to: url, options: .atomic)
            status = "Exported \(url.lastPathComponent)"
        } catch { self.error = "Export failed. \(error.localizedDescription)" }
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
                    else { self.error = failure?.localizedDescription ?? "The dropped file could not be opened." }
                }
            }
            return true
        }
        guard provider.hasItemConformingToTypeIdentifier(UTType.image.identifier) else { return false }
        provider.loadDataRepresentation(forTypeIdentifier: UTType.image.identifier) { data, failure in
            Task { @MainActor in
                guard self.generation == token else { return }
                if let data { self.read(data: data) }
                else { self.error = failure?.localizedDescription ?? "The dropped image could not be read." }
            }
        }
        return true
    }
}

enum ImageReadError: LocalizedError {
    case tooLarge
    var errorDescription: String? { "Choose an image smaller than 50 MB." }
}
