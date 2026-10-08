#if DEBUG
import Foundation
import CoreData
import Security

/// Synthetic test input/provenance only. No permissions are granted here and the
/// resolver/decoder/history used by the UI remain the production implementations.
@MainActor
enum MacSandboxDiagnostics {
    static var requested: Bool { ProcessInfo.processInfo.environment["QRCATCHER_SANDBOX_PROOF"] == "1" }
    static var sandboxed: Bool {
        guard let task = SecTaskCreateFromSelf(nil) else { return false }
        return (SecTaskCopyValueForEntitlement(task, "com.apple.security.app-sandbox" as CFString, nil) as? Bool) == true
    }
    static func prepareLegacyFixtureIfRequested() throws {
        guard let token = ProcessInfo.processInfo.environment["QRCATCHER_SANDBOX_FIXTURE"], UUID(uuidString: token) != nil else { return }
        guard requested, sandboxed else { throw QRHistoryLocationError.unsafePath }
        let home = URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true)
        let docs = try FileManager.default.url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        guard let owned = QRHistoryLocations.validatedDocuments(home: home, documents: docs, sandboxed: true) else { throw QRHistoryLocationError.unsafePath }
        let url = owned.appendingPathComponent("coredata.sqlite")
        let marker = owned.appendingPathComponent("qrcatcher-sandbox-fixture-" + token + ".marker")
        if FileManager.default.fileExists(atPath: marker.path) {
            guard try Data(contentsOf: marker) == Data(token.utf8), FileManager.default.fileExists(atPath: url.path) else { throw QRHistoryLocationError.selectedStoreMissing }
            return
        }
        guard ["", "-wal", "-shm"].allSatisfy({ !FileManager.default.fileExists(atPath: url.path + $0) }) else {
            throw NSError(domain: "QRCatcher.SandboxTest", code: 1, userInfo: [NSLocalizedDescriptionKey: "Existing Documents history retained; refusing to replace it with a synthetic fixture"])
        }
        let original = QRHistoryStore(url: url)
        guard let context = original.context else {
            if let error = original.loadError { throw error }; throw CocoaError(.fileWriteUnknown)
        }
        for seconds in [1431993600.0, 1431993500.0] {
            let row = NSEntityDescription.insertNewObject(forEntityName: "URLEntity", into: context) as! URLEntity
            row.url = "Sandbox legacy duplicate"; row.createDate = Date(timeIntervalSince1970: seconds)
        }
        try original.save(); context.reset()
        if let coordinator = context.persistentStoreCoordinator {
            for store in coordinator.persistentStores { try coordinator.remove(store) }
        }
        context.persistentStoreCoordinator = nil
        try Data(token.utf8).write(to: marker, options: .atomic)
    }
    static func evidence(actualStoreURL: URL?) -> [String: Any] {
        var result: [String: Any] = ["sandboxed": sandboxed, "home": NSHomeDirectory(), "actualStoreURL": actualStoreURL?.path ?? "unavailable"]
        guard requested, sandboxed else { return result }
        // The executable's containing directory was observed readable under the
        // exact minimal sandbox. It is not a valid negative file-access probe.
        guard let path = ProcessInfo.processInfo.environment["QRCATCHER_SANDBOX_BOUNDARY"],
              URL(fileURLWithPath: path).lastPathComponent.hasPrefix("QRCatcherBoundaryProbe-"),
              UUID(uuidString: String(URL(fileURLWithPath: path).lastPathComponent.dropFirst("QRCatcherBoundaryProbe-".count))) != nil else { return result }
        let folder = URL(fileURLWithPath: path, isDirectory: true)
        result["unselectedProbeFolder"] = folder.path
        let unselectedRead = folder.appendingPathComponent("synthetic-read.txt")
        do { _ = try Data(contentsOf: unselectedRead); result["unselectedReadRejected"] = false }
        catch {
            let error = error as NSError
            result["unselectedReadRejected"] = (error.domain == NSCocoaErrorDomain && error.code == CocoaError.fileReadNoPermission.rawValue) || (error.domain == NSPOSIXErrorDomain && [1,13].contains(error.code))
            result["readError"] = ["domain":error.domain,"code":error.code]
        }
        let unselectedWrite = folder.appendingPathComponent("qrcatcher-unselected-write-" + UUID().uuidString)
        do {
            try Data("synthetic sandbox write probe".utf8).write(to: unselectedWrite)
            try? FileManager.default.removeItem(at: unselectedWrite)
            result["unselectedWriteRejected"] = false
        } catch {
            let error = error as NSError
            result["unselectedWriteRejected"] = (error.domain == NSCocoaErrorDomain && error.code == CocoaError.fileWriteNoPermission.rawValue) || (error.domain == NSPOSIXErrorDomain && [1,13].contains(error.code))
            result["writeError"] = ["domain":error.domain,"code":error.code]
        }
        return result
    }
}
#endif
