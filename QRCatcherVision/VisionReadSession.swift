import Foundation
import Combine
import UniformTypeIdentifiers

/// One window's read/selection lifecycle. Decode uses the same proven CGImage codec.
@MainActor
final class VisionReadSession: ObservableObject {
    @Published var payload: String?
    @Published var selection: String?
    @Published var status = QRL("Import an image containing a QR code.")
    @Published var error: String?
    @Published private(set) var isReading = false
    let history: MacHistory
    private var generation = UUID()
    private let selectionCoordinator = QRSelectionCoordinator()
    private var task: Task<Void, Never>?
    private var providerProgress: Progress?
    private var providerCancellation = QRImportCancellation()

    init(history: MacHistory) { self.history = history }
    func cancel() {
        selectionCoordinator.invalidate(); generation = UUID(); task?.cancel(); task = nil; providerCancellation.cancel(); providerCancellation = QRImportCancellation(); providerProgress?.cancel(); providerProgress = nil; isReading = false }
    func beginExternalLoad() -> UUID { cancel(); isReading = true; return generation }
    func completeExternalLoad(_ token: UUID, data: Data?, error: Error?) {
        guard token == generation else { return }
        if let data { read(data: data) }
        else { isReading = false; self.error = error?.localizedDescription ?? QRL("The image could not be read.") }
    }
    func queueSelection(_ identifier: String?) {
        selectionCoordinator.enqueue(identifier) { [weak self] identifier in
            guard let self else { return }
            if let item = self.history.items.first(where: { $0.id == identifier }) { self.select(item) }
            else { self.selection = nil }
        }
    }
    func select(_ item: HistoryItem) {
        cancel(); payload = item.payload; selection = item.id; status = QRL("Saved on this device")
    }
    func read(url: URL) {
        guard url.isFileURL else { error = QRL("Only local image files can be imported."); return }
        begin {
            return try QRBoundedPhotoFile.read(url)
        }
    }
    func read(data: Data) { begin { data } }
    private func begin(load: @escaping @Sendable () throws -> Data) {
        cancel(); let token = generation; isReading = true; status = QRL("Reading image…")
        task = Task {
            do {
                let values = try await QRDecodeWorker.shared.decode(load: load)
                guard !Task.isCancelled, token == generation else { return }
                isReading = false
                guard !values.isEmpty else { status = QRL("No QR code was found. Try a clearer image with the whole code visible."); return }
                accept(values)
            } catch {
                guard !Task.isCancelled, token == generation else { return }
                isReading = false; self.error = error.localizedDescription
                status = QRL("Image could not be read. Your previous result is still available.")
            }
        }
    }
    func accept(_ values: [String]) {
        guard let first = values.first, !first.isEmpty else { return }
        cancel(); payload = first
        let saved = values.map { history.record($0) }.allSatisfy { $0 }
        selection = history.items.first(where: { $0.payload == first })?.id
        status = saved ? QRF("%d QR code(s) read and saved locally", values.count) : QRL("QR code read. Copy or export it now; history could not be saved.")
    }
    func drop(_ providers: [NSItemProvider]) -> Bool {
        guard let provider = providers.first else { return false }
        cancel(); let token = generation
        if provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, error in
                let url = (item as? URL) ?? (item as? Data).flatMap { URL(dataRepresentation: $0, relativeTo: nil) }
                Task { @MainActor in
                    guard self.generation == token else { return }
                    if let url { self.read(url: url) } else { self.error = error?.localizedDescription ?? QRL("The file could not be read.") }
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
