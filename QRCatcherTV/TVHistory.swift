import Foundation
import Combine

struct TVQRRecord: Identifiable, Codable, Equatable, Sendable {
    let id: UUID
    let payload: String
    let createdAt: Date
    let sourceAssetIdentifier: String?
}

/// TV metadata only. Large images are never placed in UserDefaults or treated as
/// durable TV Documents. This never reads, limits, or evicts the phone's history.
@MainActor
final class TVHistory: ObservableObject {
    static let byteBudget = 256 * 1024
    private struct Envelope: Codable { let version: Int; let records: [TVQRRecord] }
    @Published private(set) var items: [TVQRRecord] = []
    @Published private(set) var error: String?
    private let defaults: UserDefaults
    private let domain: String
    private let key: String
    private let budget: Int
    private var unreadable = false

    init(defaults: UserDefaults = .standard, domain: String = "100mango.QRCatcher", key: String = "QRCatcher.TV.history.v1", budget: Int = TVHistory.byteBudget) {
        self.defaults = defaults; self.domain = domain; self.key = key; self.budget = budget
        guard let existing = defaults.object(forKey: key) else { return }
        do {
            guard let data = existing as? Data, data.count <= budget else { throw StoreError.unreadable }
            let decoded = try JSONDecoder().decode(Envelope.self, from: data)
            guard decoded.version == 1, Set(decoded.records.map(\.id)).count == decoded.records.count,
                  decoded.records.allSatisfy({ !$0.payload.isEmpty && $0.createdAt.timeIntervalSince1970.isFinite }) else { throw StoreError.unreadable }
            items = decoded.records
        } catch { unreadable = true; self.error = StoreError.unreadable.localizedDescription }
    }
    static func applicationHistory() -> TVHistory {
        #if DEBUG
        if let value = ProcessInfo.processInfo.environment["QRCATCHER_TV_TEST_STORE"], UUID(uuidString: value) != nil {
            return TVHistory(key: "QRCatcher.TV.tests." + value)
        }
        #endif
        return TVHistory()
    }
    private func write(_ proposed: [TVQRRecord]) throws {
        guard !unreadable else { throw StoreError.unreadable }
        let data = try JSONEncoder().encode(Envelope(version: 1, records: proposed))
        var allValues = defaults.persistentDomain(forName: domain) ?? [:]
        allValues[key] = data
        // Account for every value in this app's persistent defaults domain, not
        // merely the history JSON. The conservative budget is below TV's warning.
        let total = try PropertyListSerialization.data(fromPropertyList: allValues, format: .binary, options: 0).count
        guard data.count <= budget, total <= budget else { throw StoreError.full }
        defaults.set(data, forKey: key)
        items = proposed; error = nil
    }
    @discardableResult
    func record(_ values: [String], sourceAssetIdentifier: String?) -> Bool {
        var proposed = items
        for payload in values where !payload.isEmpty && !proposed.contains(where: { $0.payload == payload }) {
            proposed.insert(TVQRRecord(id: UUID(), payload: payload, createdAt: Date(), sourceAssetIdentifier: sourceAssetIdentifier), at: 0)
        }
        do { try write(proposed); return true }
        catch { self.error = error.localizedDescription; return false }
    }
    func delete(_ record: TVQRRecord) {
        do { try write(items.filter { $0.id != record.id }) }
        catch { self.error = error.localizedDescription }
    }
    // Only the UI's explicit destructive confirmation calls this. No quota path
    // automatically truncates or replaces records, including unreadable data.
    func clearAfterConfirmation() {
        defaults.removeObject(forKey: key); items = []; unreadable = false; error = nil
    }
    enum StoreError: LocalizedError {
        case full, unreadable
        var errorDescription: String? {
            switch self {
            case .full: return QRL("TV history is full. Your existing records are unchanged. Scan the current QR with your phone or delete a saved record, then try again.")
            case .unreadable: return QRL("TV history could not be loaded. Its original data has not been replaced. You can still read and display a new QR code.")
            }
        }
    }
}
