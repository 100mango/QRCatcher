import Foundation
#if os(macOS)
import Security
#endif

struct QRHistoryLocationChoice: Identifiable, Sendable {
    enum Kind: String, Codable, Hashable, Sendable { case previousApp, nativeApp }
    let id: Kind
    let url: URL
    var title: String { QRL(id == .previousApp ? "Use previous app history" : "Use native app history") }
}

enum QRHistoryLocationError: LocalizedError {
    case conflict(QRHistoryLocations)
    case unsafePath
    case unreadableSelection
    case selectedStoreMissing
    var errorDescription: String? {
        switch self {
        case .conflict: return QRL("Two histories were found in this app’s container. Choose which history to use. Neither file has been replaced or erased.")
        case .unsafePath: return QRL("A history path points outside its app-owned folder. Nothing has been opened or changed.")
        case .unreadableSelection: return QRL("The saved history-location choice could not be read. Your existing history files have not been replaced or erased.")
        case .selectedStoreMissing: return QRL("The selected history file is unavailable. An empty replacement has not been created.")
        }
    }
}

/// Resolves only two explicit app-owned locations; never enumerates containers or
/// reads general Documents. Existing SQLite stores and their sidecars stay in place.
struct QRHistoryLocations: Sendable {
    let nativeURL: URL
    let previousURL: URL?
    let selectionURL: URL
    private let nativeFolder: URL
    private let previousFolder: URL?

    init(nativeURL: URL, previousURL: URL?, selectionURL: URL) {
        self.nativeURL = nativeURL; self.previousURL = previousURL; self.selectionURL = selectionURL
        nativeFolder = nativeURL.deletingLastPathComponent().resolvingSymlinksInPath().standardizedFileURL
        previousFolder = previousURL?.deletingLastPathComponent().resolvingSymlinksInPath().standardizedFileURL
    }
    private struct Selection: Codable { let version: Int; let selected: QRHistoryLocationChoice.Kind }

    var choices: [QRHistoryLocationChoice] {
        var result: [QRHistoryLocationChoice] = []
        if let previousURL { result.append(QRHistoryLocationChoice(id: .previousApp, url: previousURL)) }
        result.append(QRHistoryLocationChoice(id: .nativeApp, url: nativeURL))
        return result
    }

    static func validatedDocuments(home: URL, documents: URL, sandboxed: Bool) -> URL? {
        guard sandboxed else { return nil }
        let root = home.resolvingSymlinksInPath().standardizedFileURL
        let docs = documents.resolvingSymlinksInPath().standardizedFileURL
        guard docs.path == root.appendingPathComponent("Documents", isDirectory: true).standardizedFileURL.path else { return nil }
        return docs
    }

    static func runtime(nativeURL: URL) throws -> QRHistoryLocations {
        let home = URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true)
        #if os(macOS)
        let sandboxed: Bool
        if let task = SecTaskCreateFromSelf(nil) {
            sandboxed = (SecTaskCopyValueForEntitlement(task, "com.apple.security.app-sandbox" as CFString, nil) as? Bool) == true
        } else { sandboxed = false }
        #else
        // iOS-family apps always receive an app-specific data home from the OS.
        let sandboxed = true
        #endif
        let documents = sandboxed ? try FileManager.default.url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: false) : nil
        let owned = documents.flatMap { validatedDocuments(home: home, documents: $0, sandboxed: sandboxed) }
        return QRHistoryLocations(nativeURL: nativeURL, previousURL: owned?.appendingPathComponent("coredata.sqlite"),
                                  selectionURL: nativeURL.deletingLastPathComponent().appendingPathComponent("history-location.json"))
    }

    private func verifyPath(_ url: URL, inside folder: URL, sidecars: Bool = true) throws {
        let expected = folder.standardizedFileURL
        for suffix in sidecars ? ["", "-wal", "-shm"] : [""] {
            let path = URL(fileURLWithPath: url.path + suffix).resolvingSymlinksInPath().standardizedFileURL
            guard path.deletingLastPathComponent().path == expected.path else { throw QRHistoryLocationError.unsafePath }
        }
    }

    func resolve() throws -> URL {
        try verifyPath(nativeURL, inside: nativeFolder)
        if let previousURL, let previousFolder { try verifyPath(previousURL, inside: previousFolder) }
        try verifyPath(selectionURL, inside: nativeFolder, sidecars: false)
        let manager = FileManager.default
        if manager.fileExists(atPath: selectionURL.path) {
            do {
                let size = try selectionURL.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
                guard size <= 2048 else { throw QRHistoryLocationError.unreadableSelection }
                let saved = try JSONDecoder().decode(Selection.self, from: Data(contentsOf: selectionURL))
                guard saved.version == 1, let choice = choices.first(where: { $0.id == saved.selected }) else { throw QRHistoryLocationError.unreadableSelection }
                guard manager.fileExists(atPath: choice.url.path) else { throw QRHistoryLocationError.selectedStoreMissing }
                return choice.url
            } catch let error as QRHistoryLocationError { throw error }
            catch { throw QRHistoryLocationError.unreadableSelection }
        }
        let previousExists = previousURL.map { manager.fileExists(atPath: $0.path) } ?? false
        let nativeExists = manager.fileExists(atPath: nativeURL.path)
        if previousExists && nativeExists { throw QRHistoryLocationError.conflict(self) }
        if previousExists, let previousURL { return previousURL }
        return nativeURL
    }

    func validatedExistingChoice(_ choice: QRHistoryLocationChoice) throws -> URL {
        guard choices.contains(where: { $0.id == choice.id && $0.url == choice.url }) else { throw QRHistoryLocationError.unsafePath }
        let folder = choice.id == .previousApp ? previousFolder : nativeFolder
        guard let folder else { throw QRHistoryLocationError.unsafePath }
        try verifyPath(choice.url, inside: folder)
        guard FileManager.default.fileExists(atPath: choice.url.path) else { throw QRHistoryLocationError.selectedStoreMissing }
        return choice.url
    }

    func remember(_ choice: QRHistoryLocationChoice) throws {
        _ = try validatedExistingChoice(choice)
        try verifyPath(selectionURL, inside: nativeFolder, sidecars: false)
        let data = try JSONEncoder().encode(Selection(version: 1, selected: choice.id))
        try data.write(to: selectionURL, options: .atomic)
    }
}
