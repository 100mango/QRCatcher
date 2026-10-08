import Foundation
import Photos
import Combine

@MainActor
final class TVReadSession: ObservableObject {
    @Published var payload: String?
    @Published private(set) var decodedResults: [String] = []
    @Published private(set) var resultIndex = 0
    @Published var status = QRL("Choose a QR image from Photos.")
    @Published var error: String?
    @Published private(set) var isReading = false
    @Published private(set) var isExporting = false
    @Published private(set) var exportedAssetIdentifier: String?
    private var generation = UUID()
    private var photoRead: TVPhotoRead?
    private var decodeTask: Task<Void, Never>?
    let history: TVHistory
    init(history: TVHistory) { self.history = history }
    func cancel() { generation = UUID(); photoRead?.cancel(); photoRead = nil; decodeTask?.cancel(); decodeTask = nil; isReading = false }
    func select(_ item: TVQRRecord) { cancel(); decodedResults = [item.payload]; resultIndex = 0; payload = item.payload; status = QRL("Saved on this TV") }
    func changeResult(by delta: Int) {
        guard !decodedResults.isEmpty else { return }
        cancel(); resultIndex = (resultIndex + delta + decodedResults.count) % decodedResults.count
        payload = decodedResults[resultIndex]
    }
    func read(_ asset: PHAsset) {
        cancel(); let token = generation; isReading = true; status = QRL("Reading image…")
        guard let resource = TVPhotoLibrary.imageResource(for: asset) else { isReading = false; error = QRL("The selected photo has no readable image resource."); return }
        let identifier = asset.localIdentifier
        photoRead = TVPhotoRead(resource: resource) { result in
            Task { @MainActor in
                guard token == self.generation else { return }
                self.photoRead = nil
                switch result {
                case .failure(let error): self.isReading = false; self.error = error.localizedDescription
                case .success(let data): self.startDecode(data, sourceAssetIdentifier: identifier, token: token)
                }
            }
        }
    }
    private func startDecode(_ data: Data, sourceAssetIdentifier: String, token: UUID) {
        decodeTask = Task {
            do {
                let values = try await QRDecodeWorker.shared.decode(load: { data })
                guard !Task.isCancelled, token == generation else { return }
                isReading = false
                guard let first = values.first else { status = QRL("No QR code was found. Try a clearer image with the whole code visible."); return }
                decodedResults = values; resultIndex = 0; payload = first
                let saved = history.record(values, sourceAssetIdentifier: sourceAssetIdentifier)
                status = saved ? QRL("QR code read and saved on this TV") : QRL("QR code read. History could not be saved; scan the displayed code with your phone.")
            } catch { if !Task.isCancelled, token == generation { isReading = false; self.error = error.localizedDescription } }
        }
    }
    func export() {
        guard !isExporting, let payload else { return }
        guard let png = QRImageCodec.png(payload: payload) else { error = QRL("This result could not be represented as a QR image. Its text is still available."); return }
        isExporting = true
        let token = generation
        Task {
            do {
                let identifier = try await TVPhotoExport.saveAndVerify(png: png, payload: payload)
                exportedAssetIdentifier = identifier; status = QRL(token == generation ? "Saved to Photos and verified" : "The previously selected QR was saved to Photos and verified")
            } catch { self.error = error.localizedDescription }
            isExporting = false
        }
    }
}
