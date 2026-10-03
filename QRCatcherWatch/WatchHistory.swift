import Foundation
import Combine
import CryptoKit

struct WatchRecord: Codable, Identifiable, Equatable {
    let id: UUID
    let createdAt: Date
    let sourcePNG: Data
    let sourceSHA256: String
    var payloads: [String]
    var phoneRequest: UUID?
    var phoneState: String?
    var phoneError: String?
}
private struct WatchArchive: Codable { let version: Int; var records: [WatchRecord] }
enum WatchStoreError: LocalizedError {
    case invalidImage, imageLimit, archiveFull, invalidArchive, noQR
    var errorDescription: String? {
        switch self {
        case .invalidImage: return NSLocalizedString("This photo could not be read.", comment: "")
        case .imageLimit: return NSLocalizedString("Choose a photo up to 8 MB and 40 megapixels.", comment: "")
        case .archiveFull: return NSLocalizedString("The Watch collection is full. Remove a local item before importing another; existing items were kept.", comment: "")
        case .invalidArchive: return NSLocalizedString("The saved Watch collection could not be read. Its original file has been kept.", comment: "")
        case .noQR: return NSLocalizedString("No QR code was found. Try a clearer photo.", comment: "")
        }
    }
}
@MainActor
final class WatchHistory: ObservableObject {
    static let maximumBytes = 12 * 1024 * 1024
    static let maximumRecords = 50
    @Published private(set) var records: [WatchRecord] = []
    @Published private(set) var error: String?
    let url: URL
    private var readable = true
    init(url: URL = WatchHistory.defaultURL()) {
        self.url = url
        do {
            if FileManager.default.fileExists(atPath: url.path) {
                let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? Int.max
                guard size <= Self.maximumBytes else { throw WatchStoreError.invalidArchive }
                let archive = try JSONDecoder().decode(WatchArchive.self, from: Data(contentsOf: url))
                guard archive.version == 1, archive.records.count <= Self.maximumRecords,
                      Set(archive.records.map(\.id)).count == archive.records.count,
                      archive.records.allSatisfy({ WatchPhotoCodec.validPreparedPNG($0.sourcePNG) && Self.digest($0.sourcePNG) == $0.sourceSHA256 && $0.payloads.count <= 32 && $0.payloads.allSatisfy({ $0.utf8.count <= 16384 }) }) else { throw WatchStoreError.invalidArchive }
                records = archive.records
            }
        } catch { readable = false; self.error = WatchStoreError.invalidArchive.localizedDescription }
    }
    nonisolated static func defaultURL() -> URL {
        var name = "WatchCollection.json"
        #if DEBUG
        if let value = ProcessInfo.processInfo.environment["QRCATCHER_WATCH_STORE"], UUID(uuidString: value) != nil { name = value + ".json" }
        #endif
        return FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("QRCatcher", isDirectory: true).appendingPathComponent(name)
    }
    static func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    @discardableResult func append(source: Data, payloads: [String], date: Date = Date()) throws -> WatchRecord {
        guard WatchPhotoCodec.validPreparedPNG(source), payloads.count <= 32, payloads.allSatisfy({ $0.utf8.count <= 16384 }) else { throw WatchStoreError.imageLimit }
        let record = WatchRecord(id: UUID(), createdAt: date, sourcePNG: source, sourceSHA256: Self.digest(source), payloads: payloads)
        try commit([record] + records); return record
    }
    func replace(_ record: WatchRecord) throws {
        guard let index = records.firstIndex(where: { $0.id == record.id }), record.sourceSHA256 == records[index].sourceSHA256 else { throw WatchStoreError.invalidArchive }
        var values = records; values[index] = record; try commit(values)
    }
    func remove(_ id: UUID) throws { try commit(records.filter { $0.id != id }) }
    private func commit(_ values: [WatchRecord]) throws {
        guard readable else { throw WatchStoreError.invalidArchive }
        guard values.count <= Self.maximumRecords else { throw WatchStoreError.archiveFull }
        guard Set(values.map(\.id)).count == values.count, values.allSatisfy({
            WatchPhotoCodec.validPreparedPNG($0.sourcePNG) && Self.digest($0.sourcePNG) == $0.sourceSHA256 && $0.payloads.count <= 32 && $0.payloads.allSatisfy({ $0.utf8.count <= 16384 })
        }) else { throw WatchStoreError.invalidArchive }
        let bytes = try JSONEncoder().encode(WatchArchive(version: 1, records: values))
        guard bytes.count <= Self.maximumBytes else { throw WatchStoreError.archiveFull }
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try bytes.write(to: url, options: .atomic)
        records = values
    }
}
