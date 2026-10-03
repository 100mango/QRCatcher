import Foundation
import Combine
import CoreData

struct HistoryItem: Identifiable {
    let id: String
    let payload: String?
    let createdAt: Date?
    var text: String { payload ?? "(Empty legacy record)" }
    var webURL: URL? { payload.flatMap { QRPayload.safeWebURL($0) } }
    var exportValue: [String: Any] {
        QRHistoryValue(identifier: id, payload: payload, createdAt: createdAt).export()
    }
}

/// The original Objective-C adapter owns the untouched QR.momd schema.
/// Native Mac data is local to this Mac. It does not import or synchronize phone history.
@MainActor
final class MacHistory: ObservableObject {
    @Published private(set) var items: [HistoryItem] = []
    @Published private(set) var error: String?
    private let store: QRHistoryStore

    static func defaultURL() throws -> URL {
        #if DEBUG
        if let path = ProcessInfo.processInfo.environment["QRCATCHER_TEST_STORE"] {
            return URL(fileURLWithPath: path)
        }
        #endif
        let folder = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            .appendingPathComponent("100mango.QRCatcher", isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        return folder.appendingPathComponent("coredata.sqlite")
    }

    init(url: URL) {
        store = QRHistoryStore(url: url)
        reload()
    }

    func reload() {
        guard let context = store.context else {
            error = "History could not be loaded. Your saved data has not been erased. You can still copy or export a scanned result. Restart to retry."
            return
        }
        do {
            let request = NSFetchRequest<URLEntity>(entityName: "URLEntity")
            request.sortDescriptors = [NSSortDescriptor(key: "createDate", ascending: false)]
            items = try context.fetch(request).map {
                HistoryItem(id: $0.objectID.uriRepresentation().absoluteString, payload: $0.url, createdAt: $0.createDate)
            }
            error = nil
        } catch {
            self.error = "History could not be read: \(error.localizedDescription)"
        }
    }

    @discardableResult
    func record(_ payload: String) -> Bool {
        do {
            try store.record(payload: payload)
            reload()
            return true
        } catch {
            self.error = "QR code read, but history could not be saved. Your existing history has not been erased. \(error.localizedDescription)"
            return false
        }
    }

    func delete(_ item: HistoryItem) {
        guard let context = store.context,
              let url = URL(string: item.id),
              let id = context.persistentStoreCoordinator?.managedObjectID(forURIRepresentation: url) else { return }
        do {
            context.delete(try context.existingObject(with: id))
            try store.save()
            reload()
        } catch {
            context.rollback()
            self.error = "The record could not be deleted. \(error.localizedDescription)"
        }
    }

    func exportData() throws -> Data {
        guard error == nil else {
            throw NSError(domain: "QRCatcher.History", code: 2, userInfo: [NSLocalizedDescriptionKey: "History is unavailable. Export the current QR result instead; your saved data has not been erased."])
        }
        // Export all records in displayed order, including null legacy values, without deduplication.
        return try JSONSerialization.data(withJSONObject: ["format": "QRCatcher.history", "version": 1,
            "records": items.map(\.exportValue)], options: [.prettyPrinted, .sortedKeys])
    }
}
