import Foundation
import Combine
import CoreData

struct HistoryItem: Identifiable {
    let id: String
    let payload: String?
    let createdAt: Date?
    var text: String { payload ?? QRL("(Empty legacy record)") }
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
    @Published private(set) var locationChoices: [QRHistoryLocationChoice] = []
    private var store: QRHistoryStore?
    private var locations: QRHistoryLocations?

    static func defaultURL() throws -> URL {
        #if DEBUG
        if let path = ProcessInfo.processInfo.environment["QRCATCHER_TEST_STORE"] {
            return URL(fileURLWithPath: path)
        }
        #endif
        let support = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        let folder = support.appendingPathComponent("100mango.QRCatcher", isDirectory: true)
        let expected = support.resolvingSymlinksInPath().appendingPathComponent("100mango.QRCatcher", isDirectory: true).standardizedFileURL
        guard folder.resolvingSymlinksInPath().standardizedFileURL.path == expected.path else { throw QRHistoryLocationError.unsafePath }
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        #if DEBUG
        if let name = ProcessInfo.processInfo.environment["QRCATCHER_TEST_STORE_NAME"], UUID(uuidString: name) != nil {
            return folder.appendingPathComponent("ui-testing-\(name).sqlite")
        }
        #endif
        return try QRHistoryLocations.runtime(nativeURL: folder.appendingPathComponent("coredata.sqlite")).resolve()
    }

    static func applicationHistory() -> MacHistory {
        do { return MacHistory(url: try defaultURL()) }
        catch QRHistoryLocationError.conflict(let locations) { return MacHistory(conflict: locations) }
        catch { return MacHistory(loadFailure: error.localizedDescription) }
    }

    private init(loadFailure: String) { error = loadFailure }
    private init(conflict: QRHistoryLocations) {
        locations = conflict
        locationChoices = conflict.choices
        error = QRHistoryLocationError.conflict(conflict).localizedDescription
    }

    func chooseLocation(_ choice: QRHistoryLocationChoice) {
        guard let locations, locationChoices.contains(where: { $0.id == choice.id }) else { return }
        do {
            let selectedURL = try locations.validatedExistingChoice(choice)
            let candidate = QRHistoryStore(url: selectedURL)
            guard candidate.loadError == nil else {
                error = QRL("The chosen history could not be loaded. Neither history file has been replaced or erased.")
                return
            }
            try locations.remember(choice)
            store = candidate
            locationChoices = []
            reload()
        } catch { self.error = error.localizedDescription }
    }

    init(url: URL) {
        store = QRHistoryStore(url: url)
        reload()
    }

    func reload() {
        guard let context = store?.context else {
            if store == nil, error != nil { return }
            error = QRL("History could not be loaded. Your saved data has not been erased. You can still copy or export a scanned result. Restart to retry.")
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
            self.error = QRF("History could not be read: %@", error.localizedDescription)
        }
    }

    @discardableResult
    func record(_ payload: String) -> Bool {
        guard let store else { return false }
        do {
            try store.record(payload: payload)
            reload()
            return true
        } catch {
            self.error = QRF("QR code read, but history could not be saved. Your existing history has not been erased. %@", error.localizedDescription)
            return false
        }
    }

    func delete(_ item: HistoryItem) {
        guard let store, let context = store.context,
              let url = URL(string: item.id),
              let id = context.persistentStoreCoordinator?.managedObjectID(forURIRepresentation: url) else { return }
        do {
            context.delete(try context.existingObject(with: id))
            try store.save()
            reload()
        } catch {
            context.rollback()
            self.error = QRF("The record could not be deleted. %@", error.localizedDescription)
        }
    }

    /// Disconnect cleanly before a fixture directory or temporary history is
    /// removed. Pending changes must save successfully; closing never deletes data.
    func close() throws {
        if let context = store?.context {
            if context.hasChanges { try context.save() }
            context.reset()
            if let coordinator = context.persistentStoreCoordinator {
                for persistent in coordinator.persistentStores { try coordinator.remove(persistent) }
            }
            context.persistentStoreCoordinator = nil
        }
        store = nil
    }

    func exportData() throws -> Data {
        guard error == nil else {
            throw NSError(domain: "QRCatcher.History", code: 2, userInfo: [NSLocalizedDescriptionKey: QRL("History is unavailable. Export the current QR result instead; your saved data has not been erased.")])
        }
        // Export all records in displayed order, including null legacy values, without deduplication.
        return try JSONSerialization.data(withJSONObject: ["format": "QRCatcher.history", "version": 1,
            "records": items.map(\.exportValue)], options: [.prettyPrinted, .sortedKeys])
    }
}
