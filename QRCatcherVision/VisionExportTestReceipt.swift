#if DEBUG
import Foundation
import CryptoKit

/// Read-only observer of the real system FileExporter completion. It never
/// creates the exported document or substitutes bytes for the system save.
/// Only an explicitly isolated XCTest store enables this bounded receipt.
enum VisionExportTestReceipt {
    static func observe(_ selectedURL: URL) throws {
        guard let name = ProcessInfo.processInfo.environment["QRCATCHER_TEST_STORE_NAME"],
              UUID(uuidString: name) != nil else { return }
        let scoped = selectedURL.startAccessingSecurityScopedResource()
        defer { if scoped { selectedURL.stopAccessingSecurityScopedResource() } }
        let values = try selectedURL.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard values.isRegularFile == true, values.isSymbolicLink != true,
              let count = values.fileSize, count > 0, count <= 2 * 1024 * 1024,
              ["png", "json"].contains(selectedURL.pathExtension.lowercased()) else {
            throw NSError(domain: "QRCatcher.ExportTest", code: 1)
        }
        let handle = try FileHandle(forReadingFrom: selectedURL); defer { try? handle.close() }
        var data = Data()
        while let chunk = try handle.read(upToCount: 64 * 1024), !chunk.isEmpty {
            guard data.count + chunk.count <= 2 * 1024 * 1024 else { throw NSError(domain: "QRCatcher.ExportTest", code: 2) }
            data.append(chunk)
        }
        let folder = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("QRCatcherExportTestReceipts", isDirectory: true).appendingPathComponent(name, isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let type = selectedURL.pathExtension.lowercased()
        try data.write(to: folder.appendingPathComponent("saved." + type), options: .atomic)
        let receipt: [String: Any] = ["test_store": name, "type": type, "bytes": data.count,
            "sha256": SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(),
            "source": "Actual system FileExporter completion URL readback"]
        try JSONSerialization.data(withJSONObject: receipt, options: .sortedKeys)
            .write(to: folder.appendingPathComponent(type + ".json"), options: .atomic)
    }
}
#endif
