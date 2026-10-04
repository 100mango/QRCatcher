import Foundation
import Combine
import WatchConnectivity

/// A fresh snapshot of the system queue, with cancellation owned by that transfer.
/// Production reads WCSession each time, including after a process relaunch.
struct WatchQueuedFileTransfer {
    let metadata: [String: Any]?
    let cancel: () -> Void
}
private struct WatchRequestIdentity: Sendable {
    let recordID: UUID
    let requestID: UUID
    let sourceSHA256: String
    init?(metadata: [String: Any]?) {
        guard metadata?["kind"] as? String == "qrcatcher.decode.request", metadata?["version"] as? Int == 1,
              let record = (metadata?["recordID"] as? String).flatMap(UUID.init(uuidString:)),
              let request = (metadata?["requestID"] as? String).flatMap(UUID.init(uuidString:)),
              let hash = metadata?["sourceSHA256"] as? String else { return nil }
        recordID = record; requestID = request; sourceSHA256 = hash
    }
    func matches(_ record: WatchRecord) -> Bool {
        recordID == record.id && requestID == record.phoneRequest && sourceSHA256 == record.sourceSHA256
    }
}

/// Background delivery uses the real paired-device file API. Simulator callbacks
/// are not supported by Apple and are not claimed as an E2E transport test.
@MainActor
final class WatchPhoneTransport: NSObject, ObservableObject, WCSessionDelegate {
    @Published private(set) var status = ""
    private let history: WatchHistory
    private let session = WCSession.default
    private let outstandingTransfers: () -> [WatchQueuedFileTransfer]
    private let folder: URL
    nonisolated private let inbox: WatchReplyJournal
    convenience init(history: WatchHistory) {
        self.init(history: history, outstandingTransfers: {
            WCSession.default.outstandingFileTransfers.map { transfer in
                WatchQueuedFileTransfer(metadata: transfer.file.metadata, cancel: { transfer.cancel() })
            }
        }, activateSession: true)
    }
    #if DEBUG
    /// Deterministic queue ownership tests never activate a real WC session or
    /// claim simulator file delivery. This injection entry is absent in Release.
    convenience init(history: WatchHistory, outstandingTransfers: @escaping () -> [WatchQueuedFileTransfer]) {
        self.init(history: history, outstandingTransfers: outstandingTransfers, activateSession: false)
    }
    #endif
    private init(history: WatchHistory, outstandingTransfers: @escaping () -> [WatchQueuedFileTransfer], activateSession: Bool) {
        self.history = history
        self.outstandingTransfers = outstandingTransfers
        folder = history.url.deletingLastPathComponent().appendingPathComponent("PhoneRequests", isDirectory: true)
        inbox = WatchReplyJournal(folder: WatchReplyJournal.location(for: history.url))
        super.init()
        do { try replayPendingReplies(); reconcileCancelledTransfers() } catch { status = error.localizedDescription }
        guard activateSession, WCSession.isSupported() else { return }
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
        // Commit the tombstone first so an already-delivered delayed reply cannot
        // resurrect this job. Activation/relaunch repeats transport cleanup if a
        // process interruption occurs after this commit but before cancellation.
        record.phoneState = "cancelled"; try history.replace(record)
        cancelTransfers(for: record)
        try? FileManager.default.removeItem(at: folder.appendingPathComponent(request.uuidString + ".png"))
        status = NSLocalizedString("Cancelled", comment: "")
    }
    private func cancelTransfers(for record: WatchRecord) {
        for transfer in outstandingTransfers() where WatchRequestIdentity(metadata: transfer.metadata)?.matches(record) == true { transfer.cancel() }
    }
    private func reconcileCancelledTransfers() {
        for record in history.records where record.phoneState == "cancelled" {
            cancelTransfers(for: record)
            if let request = record.phoneRequest {
                try? FileManager.default.removeItem(at: folder.appendingPathComponent(request.uuidString + ".png"))
            }
        }
    }
    private func enqueue(_ record: WatchRecord, path: URL) {
        guard let request = record.phoneRequest else { return }
        session.transferFile(path, metadata: ["kind":"qrcatcher.decode.request", "version":1, "recordID":record.id.uuidString, "requestID":request.uuidString, "sourceSHA256":record.sourceSHA256])
        status = NSLocalizedString("Waiting for paired iPhone. Keep both apps installed; delivery may happen later.", comment: "")
    }
    nonisolated func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        Task { @MainActor in
            if let error { self.status = error.localizedDescription }
            do { try self.replayPendingReplies(); self.reconcileCancelledTransfers() } catch { self.status = error.localizedDescription }
            // Activation never resends a retained request to a changed phone.
            // The user can cancel and explicitly retry from the record screen.
        }
    }
    nonisolated func session(_ session: WCSession, didReceive file: WCSessionFile) {
        // Copy the bounded temporary result before this delegate callback returns.
        do {
            let bytes = try Self.readBoundedReply(file.fileURL)
            try inbox.stage(bytes) // Atomic durable write BEFORE returning from the WC delegate.
            Task { @MainActor in do { try self.replayPendingReplies() } catch { self.status = error.localizedDescription } }
        } catch { Task { @MainActor in self.status = error.localizedDescription } }
    }
    nonisolated static func readBoundedReply(_ url: URL) throws -> Data { try WatchReplyJournal.read(url) }
    func replayPendingReplies() throws {
        // Read locally only. A replay never enqueues anything to the current or
        // a newly paired counterpart. Failed history writes retain the journal.
        guard history.error == nil else { throw WatchStoreError.invalidArchive }
        for url in try inbox.pending() {
            let bytes = try inbox.read(url)
            try accept(bytes)
            // Both a durable accepted result and a validated obsolete request
            // can be removed. A kill before this point only causes an idempotent
            // replay against the already-completed persisted history record.
            try inbox.finish(url, expected: bytes)
        }
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
        guard let values = result["payloads"] as? [String],
              let outcome = result["status"] as? String,
              ["completed", "no_qr", "invalid_image"].contains(outcome),
              (outcome == "completed") == !values.isEmpty else { return }
        guard values.count <= 32, values.allSatisfy({ !$0.isEmpty && $0.utf8.count <= 16384 }) else { throw WatchStoreError.imageLimit }
        // An unsuccessful explicit phone retry must not erase a result already
        // decoded locally or returned by a previous successful phone request.
        if !values.isEmpty { record.payloads = values }
        record.phoneState = values.isEmpty ? "failed" : "completed"
        record.phoneError = values.isEmpty ? NSLocalizedString("iPhone could not read a QR code. Existing results and the saved photo were kept.", comment: "") : nil
        try history.replace(record)
        try? FileManager.default.removeItem(at: folder.appendingPathComponent(requestID.uuidString + ".png"))
        status = values.isEmpty ? record.phoneError! : NSLocalizedString("iPhone result saved on this Watch", comment: "")
    }
    nonisolated func session(_ session: WCSession, didFinish fileTransfer: WCSessionFileTransfer, error: Error?) {
        guard let error else { return } // Completion is not a decoded-result acknowledgement.
        guard let identity = WatchRequestIdentity(metadata: fileTransfer.file.metadata) else { return }
        Task { @MainActor in
            guard var record = self.history.records.first(where: { $0.phoneState == "pending" && identity.matches($0) }) else { return }
            record.phoneState = "failed"; record.phoneError = error.localizedDescription
            do { try self.history.replace(record) } catch { self.status = error.localizedDescription }
        }
    }
}
