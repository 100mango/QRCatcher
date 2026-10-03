import XCTest
import Foundation
import CoreData
import Security
@testable import QRCatcherMac

/// Executed only by the separate ad-hoc-signed App Sandbox scheme. The ordinary
/// unsigned suite cannot count these as passes or substitute its /tmp store.
@MainActor
final class QRCatcherMacSandboxTests: QRManagedStoreTestCase {
    private func verifySandbox() throws -> URL {
        let task = try XCTUnwrap(SecTaskCreateFromSelf(nil))
        XCTAssertEqual(SecTaskCopyValueForEntitlement(task, "com.apple.security.app-sandbox" as CFString, nil) as? Bool, true)
        XCTAssertEqual(Bundle.main.bundleIdentifier, "100mango.QRCatcher")
        let home = URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true).resolvingSymlinksInPath()
        let support = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        XCTAssertTrue(support.resolvingSymlinksInPath().path.hasPrefix(home.path + "/"))
        print("ACTUAL_SANDBOX_CONTAINER:", home.path, "APPLICATION_SUPPORT:", support.path)
        return support
    }
    private func temporaryFolder() throws -> URL {
        let folder = try verifySandbox().appendingPathComponent("QRCatcher-SandboxTest-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        cleanupLater(folder)
        return folder
    }
    func testActualContainerDefaultAndDurableHistory() throws {
        let support = try verifySandbox()
        let actualDefault = try MacHistory.defaultURL()
        XCTAssertTrue(actualDefault.resolvingSymlinksInPath().path.hasPrefix(support.resolvingSymlinksInPath().path + "/"))
        let url = try temporaryFolder().appendingPathComponent("coredata.sqlite")
        let history = makeHistory(url: url)
        XCTAssertNil(history.error); XCTAssertTrue(history.record("Sandbox local result 你好"))
        let reopened = makeHistory(url: url)
        XCTAssertNil(reopened.error); XCTAssertEqual(reopened.items.first?.payload, "Sandbox local result 你好")
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: reopened.exportData()) as? [String: Any])
        XCTAssertEqual((json["records"] as? [[String: Any]])?.count, 1)
        print("ACTUAL_SANDBOX_STORE:", url.path)
    }
    func testActualOwnedDocumentsLegacySelectionPreservesSidecarsAndDuplicates() throws {
        _ = try verifySandbox()
        let docs = try FileManager.default.url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        let legacy = docs.appendingPathComponent("coredata.sqlite")
        let paths = ["", "-wal", "-shm"].map { URL(fileURLWithPath: legacy.path + $0) }
        guard paths.allSatisfy({ !FileManager.default.fileExists(atPath: $0.path) }) else {
            throw NSError(domain: "QRCatcher.SandboxTests", code: 1, userInfo: [NSLocalizedDescriptionKey: "Existing legacy files retained; refusing to replace them with a test fixture"])
        }
        for path in paths { cleanupLater(path) }
        let old = makeLegacyStore(url: legacy)
        let context = try XCTUnwrap(old.context)
        for seconds in [1431993600.0,1431993500.0] {
            let row = NSEntityDescription.insertNewObject(forEntityName: "URLEntity", into: context) as! URLEntity
            row.url = "Sandbox legacy duplicate"; row.createDate = Date(timeIntervalSince1970: seconds)
        }
        try old.save()
        let bytes = try paths.map { try Data(contentsOf: $0) }
        let native = try temporaryFolder().appendingPathComponent("coredata.sqlite")
        let locations = try QRHistoryLocations.runtime(nativeURL: native)
        XCTAssertEqual(locations.previousURL?.resolvingSymlinksInPath(), legacy.resolvingSymlinksInPath())
        XCTAssertEqual(try locations.resolve(), legacy)
        XCTAssertEqual(try paths.map { try Data(contentsOf: $0) }, bytes)
        let reopened = makeHistory(url: try locations.resolve())
        XCTAssertNil(reopened.error)
        XCTAssertEqual(reopened.items.map(\.payload), ["Sandbox legacy duplicate", "Sandbox legacy duplicate"])
        XCTAssertEqual(reopened.items.compactMap { $0.createdAt?.timeIntervalSince1970 }, [1431993600,1431993500])
        XCTAssertFalse(FileManager.default.fileExists(atPath: native.path))
    }
    func testSandboxDeniesAnUnselectedWriteOutsideItsContainer() throws {
        _ = try verifySandbox()
        let unselected = Bundle.main.bundleURL.deletingLastPathComponent().appendingPathComponent("qrcatcher-sandbox-denial-" + UUID().uuidString)
        do {
            try Data("synthetic sandbox probe".utf8).write(to: unselected)
            try? FileManager.default.removeItem(at: unselected)
            XCTFail("An unselected sibling path outside the application/container was writable")
        } catch {
            let failure = error as NSError
            XCTAssertTrue((failure.domain == NSCocoaErrorDomain && failure.code == CocoaError.fileWriteNoPermission.rawValue) || (failure.domain == NSPOSIXErrorDomain && [1,13].contains(failure.code)), "Expected an actual permission denial, not a missing-path failure: \(failure)")
            print("SANDBOX_WRITE_DENIAL:", failure.domain, failure.code)
        }
    }
}
