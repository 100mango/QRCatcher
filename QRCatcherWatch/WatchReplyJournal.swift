import Foundation

/// Incoming WC files cease to exist when the delegate returns. This bounded,
/// app-owned inbox crosses that delivery boundary before MainActor history work.
final class WatchReplyJournal: @unchecked Sendable {
    static let replyLimit = 2 * 1024 * 1024
    static let totalLimit = 8 * 1024 * 1024
    static let countLimit = 32
    static func location(for historyURL: URL) -> URL {
        historyURL.deletingLastPathComponent().appendingPathComponent(historyURL.lastPathComponent + ".incoming", isDirectory: true)
    }
    let folder: URL
    private let lock = NSLock()
    init(folder: URL) { self.folder = folder }

    @discardableResult func stage(_ bytes: Data) throws -> URL {
        guard !bytes.isEmpty, bytes.count <= Self.replyLimit,
              let value = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              value["kind"] as? String == "qrcatcher.decode.result", value["version"] as? Int == 1,
              let request = (value["requestID"] as? String).flatMap(UUID.init(uuidString:)),
              (value["recordID"] as? String).flatMap(UUID.init(uuidString:)) != nil,
              let hash = value["sourceSHA256"] as? String, hash.count == 64,
              hash.allSatisfy({ $0.isHexDigit }) else { throw WatchStoreError.invalidArchive }
        lock.lock(); defer { lock.unlock() }
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let entries = try inventory()
        let destination = folder.appendingPathComponent(request.uuidString + ".reply.json")
        if entries.contains(where: { $0.url == destination }) {
            // A duplicate is idempotent. A conflicting same-ID reply must never
            // replace the first durable reply before that original is validated.
            guard try Self.read(destination) == bytes else { throw WatchStoreError.invalidArchive }
            return destination
        }
        guard entries.count < Self.countLimit,
              entries.reduce(0, { $0 + $1.bytes }) + bytes.count <= Self.totalLimit else { throw WatchStoreError.archiveFull }
        try bytes.write(to: destination, options: .atomic)
        return destination
    }
    func pending() throws -> [URL] {
        lock.lock(); defer { lock.unlock() }
        return try inventory().map(\.url)
    }
    func read(_ url: URL) throws -> Data {
        lock.lock(); defer { lock.unlock() }
        guard url.deletingLastPathComponent().standardizedFileURL == folder.standardizedFileURL else { throw WatchStoreError.invalidArchive }
        return try Self.read(url)
    }
    func finish(_ url: URL, expected: Data) throws {
        lock.lock(); defer { lock.unlock() }
        guard url.deletingLastPathComponent().standardizedFileURL == folder.standardizedFileURL,
              try Self.read(url) == expected else { throw WatchStoreError.invalidArchive }
        try FileManager.default.removeItem(at: url)
    }
    private func inventory() throws -> [(url: URL, bytes: Int)] {
        guard FileManager.default.fileExists(atPath: folder.path) else { return [] }
        let info = try folder.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
        guard info.isDirectory == true, info.isSymbolicLink != true else { throw WatchStoreError.invalidArchive }
        let files = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.fileSizeKey, .isRegularFileKey, .isSymbolicLinkKey])
        guard files.count <= Self.countLimit else { throw WatchStoreError.archiveFull }
        var result: [(URL, Int)] = [], total = 0
        for file in files.sorted(by: { $0.lastPathComponent < $1.lastPathComponent }) {
            let name = file.lastPathComponent
            guard name.hasSuffix(".reply.json"), UUID(uuidString: String(name.dropLast(".reply.json".count))) != nil else { throw WatchStoreError.invalidArchive }
            let properties = try file.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey, .isSymbolicLinkKey])
            guard properties.isRegularFile == true, properties.isSymbolicLink != true,
                  let size = properties.fileSize, size > 0, size <= Self.replyLimit else { throw WatchStoreError.invalidArchive }
            total += size; guard total <= Self.totalLimit else { throw WatchStoreError.archiveFull }
            result.append((file, size))
        }
        return result
    }
    static func read(_ url: URL) throws -> Data {
        let info = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard info.isRegularFile == true, info.isSymbolicLink != true,
              let size = info.fileSize, size > 0, size <= replyLimit else { throw WatchStoreError.invalidArchive }
        let handle = try FileHandle(forReadingFrom: url); defer { try? handle.close() }
        var bytes = Data()
        while let chunk = try handle.read(upToCount: 64 * 1024), !chunk.isEmpty {
            guard chunk.count <= replyLimit - bytes.count else { throw WatchStoreError.invalidArchive }
            bytes.append(chunk)
        }
        return bytes
    }
}
