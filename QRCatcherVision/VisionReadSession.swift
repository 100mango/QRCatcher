import Foundation
import Combine
import UniformTypeIdentifiers

/// One window's read/selection lifecycle. Decode uses the same proven CGImage codec.
@MainActor
final class VisionReadSession: ObservableObject {
    @Published var payload: String?
    @Published var selection: String?
    @Published var status = "Import an image containing a QR code."
    @Published var error: String?
    @Published private(set) var isReading = false
    let history: MacHistory
    private var generation = UUID()
    private var task: Task<Void, Never>?
    private var providerProgress: Progress?

    init(history: MacHistory) { self.history = history }
    func cancel() { generation = UUID(); task?.cancel(); task = nil; providerProgress?.cancel(); providerProgress = nil; isReading = false }
    func beginExternalLoad() -> UUID { cancel(); isReading = true; return generation }
    func completeExternalLoad(_ token: UUID, data: Data?, error: Error?) {
        guard token == generation else { return }
        if let data { read(data: data) }
        else { isReading = false; self.error = error?.localizedDescription ?? QRL("The image could not be read.") }
    }
    func select(_ item: HistoryItem) {
        cancel(); payload = item.payload; selection = item.id; status = "Saved on this device"
    }
    func read(url: URL) {
        guard url.isFileURL else { error = "Only local image files can be imported."; return }
        begin {
            let access = url.startAccessingSecurityScopedResource()
            defer { if access { url.stopAccessingSecurityScopedResource() } }
            guard (try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0) <= 50 * 1024 * 1024 else {
                throw NSError(domain: "QRCatcher.Image", code: 1, userInfo: [NSLocalizedDescriptionKey: "Choose an image smaller than 50 MB."])
            }
            return try Data(contentsOf: url, options: .mappedIfSafe)
        }
    }
    func read(data: Data) { begin { data } }
    private func begin(load: @escaping @Sendable () throws -> Data) {
        cancel(); let token = generation; isReading = true; status = "Reading image…"
        task = Task {
            do {
                let values = try await QRDecodeWorker.shared.decode(load: load)
                guard !Task.isCancelled, token == generation else { return }
                isReading = false
                guard !values.isEmpty else { status = "No QR code was found. Try a clearer image with the whole code visible."; return }
                accept(values)
            } catch {
                guard !Task.isCancelled, token == generation else { return }
                isReading = false; self.error = error.localizedDescription
                status = "Image could not be read. Your previous result is still available."
            }
        }
    }
    func accept(_ values: [String]) {
        guard let first = values.first, !first.isEmpty else { return }
        cancel(); payload = first
        let saved = values.map { history.record($0) }.allSatisfy { $0 }
        selection = history.items.first(where: { $0.payload == first })?.id
        status = saved ? "\(values.count) QR code\(values.count == 1 ? "" : "s") read and saved locally" : "QR code read. Copy or export it now; history could not be saved."
    }
    func drop(_ providers: [NSItemProvider]) -> Bool {
        guard let provider = providers.first else { return false }
        cancel(); let token = generation
        if provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, error in
                let url = (item as? URL) ?? (item as? Data).flatMap { URL(dataRepresentation: $0, relativeTo: nil) }
                Task { @MainActor in
                    guard self.generation == token else { return }
                    if let url { self.read(url: url) } else { self.error = error?.localizedDescription ?? "The file could not be read." }
                }
            }
            return true
        }
        guard provider.hasItemConformingToTypeIdentifier(UTType.image.identifier) else { return false }
        providerProgress = provider.loadDataRepresentation(forTypeIdentifier: UTType.image.identifier) { data, error in
            Task { @MainActor in
                guard self.generation == token else { return }
                if let data { self.read(data: data) } else { self.error = error?.localizedDescription ?? "The image could not be read." }
            }
        }
        return true
    }
}
