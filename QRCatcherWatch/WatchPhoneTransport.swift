import Foundation
import Combine
import WatchConnectivity

/// Background delivery uses the real paired-device file API. Simulator callbacks
/// are not supported by Apple and are not claimed as an E2E transport test.
@MainActor
final class WatchPhoneTransport: NSObject, ObservableObject, WCSessionDelegate {
    @Published private(set) var status = ""
    private let history: WatchHistory
    private let session = WCSession.default
    private let folder: URL
    init(history: WatchHistory) {
        self.history = history
        folder = history.url.deletingLastPathComponent().appendingPathComponent("PhoneRequests", isDirectory: true)
        super.init()
        guard WCSession.isSupported() else { return }
        session.delegate = self; session.activate()
    }
    func request(_ id: UUID) throws {
        guard var record = history.records.first(where: { $0.id == id }) else { return }
        guard WCSession.isSupported(), session.activationState == .activated, session.isCompanionAppInstalled else {
            status = NSLocalizedString("Open QRCatcher on your paired iPhone, then try again.", comment: ""); return
        }
        guard record.phoneState != "pending" else { return }
        if record.phoneRequest != nil { try cancel(id) } // discard only an obsolete transport copy; original photo remains durable
        let request = UUID()
        let path = folder.appendingPathComponent(request.uuidString + ".png")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        try record.sourcePNG.write(to: path, options: .atomic)
        record.phoneRequest = request; record.phoneState = "pending"; record.phoneError = nil
        do { try history.replace(record) } catch { try? FileManager.default.removeItem(at: path); throw error }
        enqueue(record, path: path)
    }
    func cancel(_ id: UUID) throws {
        guard var record = history.records.first(where: { $0.id == id }), let request = record.phoneRequest else { return }
        for transfer in session.outstandingFileTransfers where transfer.file.metadata?["requestID"] as? String == request.uuidString { transfer.cancel() }
        record.phoneState = "cancelled"; try history.replace(record)
        try? FileManager.default.removeItem(at: folder.appendingPathComponent(request.uuidString + ".png"))
    }
    private func enqueue(_ record: WatchRecord, path: URL) {
        guard let request = record.phoneRequest else { return }
        session.transferFile(path, metadata: ["kind":"qrcatcher.decode.request", "version":1, "recordID":record.id.uuidString, "requestID":request.uuidString, "sourceSHA256":record.sourceSHA256])
        status = NSLocalizedString("Waiting for paired iPhone. Keep both apps installed; delivery may happen later.", comment: "")
    }
    nonisolated func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        Task { @MainActor in
            if let error { self.status = error.localizedDescription }
            // Activation never resends a retained request to a changed phone.
            // The user can cancel and explicitly retry from the record screen.
        }
    }
    nonisolated func session(_ session: WCSession, didReceive file: WCSessionFile) {
        // Copy the bounded temporary result before this delegate callback returns.
        do {
            let size = try file.fileURL.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? Int.max
            guard size <= 2 * 1024 * 1024 else { return }
            let bytes = try Data(contentsOf: file.fileURL)
            Task { @MainActor in do { try self.accept(bytes) } catch { self.status = error.localizedDescription } }
        } catch { Task { @MainActor in self.status = error.localizedDescription } }
    }
    func accept(_ bytes: Data) throws {
        guard bytes.count <= 2 * 1024 * 1024,
              let result = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              result["kind"] as? String == "qrcatcher.decode.result", result["version"] as? Int == 1,
              let recordID = (result["recordID"] as? String).flatMap(UUID.init(uuidString:)),
              let requestID = (result["requestID"] as? String).flatMap(UUID.init(uuidString:)),
              var record = history.records.first(where: { $0.id == recordID }),
              record.phoneState == "pending", record.phoneRequest == requestID,
              result["sourceSHA256"] as? String == record.sourceSHA256 else { return }
        let values = result["payloads"] as? [String] ?? []
        guard values.count <= 32, values.allSatisfy({ $0.utf8.count <= 16384 }) else { throw WatchStoreError.imageLimit }
        record.payloads = values
        record.phoneState = values.isEmpty ? "failed" : "completed"
        record.phoneError = values.isEmpty ? NSLocalizedString("No QR code was found on iPhone. Try a clearer photo.", comment: "") : nil
        try history.replace(record)
        try? FileManager.default.removeItem(at: folder.appendingPathComponent(requestID.uuidString + ".png"))
        status = values.isEmpty ? record.phoneError! : NSLocalizedString("iPhone result saved on this Watch", comment: "")
    }
    nonisolated func session(_ session: WCSession, didFinish fileTransfer: WCSessionFileTransfer, error: Error?) {
        guard let error else { return } // Completion is not a decoded-result acknowledgement.
        let request = fileTransfer.file.metadata?["requestID"] as? String
        Task { @MainActor in
            guard var record = self.history.records.first(where: { $0.phoneRequest?.uuidString == request && $0.phoneState == "pending" }) else { return }
            record.phoneState = "failed"; record.phoneError = error.localizedDescription
            do { try self.history.replace(record) } catch { self.status = error.localizedDescription }
        }
    }
}
