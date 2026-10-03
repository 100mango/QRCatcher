import XCTest
import CoreData
import AppKit
@testable import QRCatcherMac

@MainActor
final class QRCatcherMacTests: XCTestCase {
    private func directory() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }

    func testSafePayloadPolicy() {
        XCTAssertEqual(QRPayload.safeWebURL("example.com")?.absoluteString, "https://example.com")
        XCTAssertNotNil(QRPayload.safeWebURL("HTTPS://example.com/a?q=1"))
        for text in ["", "plain text", "javascript:alert(1)", "file:///etc/passwd", "tel:123", "https://user:secret@example.com", "http://"] {
            XCTAssertNil(QRPayload.safeWebURL(text), text)
        }
    }

    func testIndependentGoldenImages() throws {
        let expected = ["ascii": ["https://example.com/qrcatcher?source=golden"], "unicode": ["QRCatcher 你好 🌈 123"],
                        "rotated": ["QRCatcher 你好 🌈 123"], "invalid": [],
                        "multiple": ["https://example.com/qrcatcher?source=golden", "QRCatcher 你好 🌈 123"]]
        for (name, payloads) in expected {
            let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: name, withExtension: "png"))
            XCTAssertEqual(Set(try QRImageCodec.decode(data: Data(contentsOf: url))), Set(payloads), name)
        }
    }

    func testExportedPNGRescansAndHasQuietZone() throws {
        for value in ["https://example.com/", "QRCatcher 你好 🌈 123", "javascript:alert(1)"] {
            let data = try XCTUnwrap(QRImageCodec.png(payload: value))
            XCTAssertEqual(try QRImageCodec.decode(data: data), [value])
            let image = try XCTUnwrap(NSBitmapImageRep(data: data))
            for point in [(0,0), (31,31), (image.pixelsWide-1,image.pixelsHigh-1)] {
                let color = try XCTUnwrap(image.colorAt(x: point.0, y: point.1)?.usingColorSpace(.deviceRGB))
                XCTAssertEqual(color.redComponent, 1, accuracy: 0.001)
                XCTAssertEqual(color.greenComponent, 1, accuracy: 0.001)
            }
        }
        XCTAssertNil(QRImageCodec.png(payload: ""))
        XCTAssertThrowsError(try QRImageCodec.decode(data: Data("not an image".utf8)))
        XCTAssertThrowsError(try QRImageCodec.decode(data: Data(count: 50 * 1024 * 1024 + 1)))
    }

    func testLegacyModelAndHistoryPreserveNullDateDuplicatesAndReopen() throws {
        let url = try directory().appendingPathComponent("coredata.sqlite")
        let model = QRHistoryStore.model()
        XCTAssertEqual(Set(model.entitiesByName.keys), ["URLEntity"])
        XCTAssertEqual(Set(try XCTUnwrap(model.entitiesByName["URLEntity"]).attributesByName.keys), ["url", "createDate"])
        let coordinator = NSPersistentStoreCoordinator(managedObjectModel: model)
        let persistent = try coordinator.addPersistentStore(ofType: NSSQLiteStoreType, configurationName: nil, at: url, options: nil)
        let context = NSManagedObjectContext(concurrencyType: .mainQueueConcurrencyType)
        context.persistentStoreCoordinator = coordinator
        for (text, date) in [("legacy duplicate", Date(timeIntervalSince1970: 1431993600)), ("legacy duplicate", Date(timeIntervalSince1970: 1431993500)), ("oldest", Date(timeIntervalSince1970: 0))] {
            let record = NSEntityDescription.insertNewObject(forEntityName: "URLEntity", into: context) as! URLEntity
            record.url = text; record.createDate = date
        }
        _ = NSEntityDescription.insertNewObject(forEntityName: "URLEntity", into: context)
        try context.save(); context.reset(); try coordinator.remove(persistent)
        var history: MacHistory? = MacHistory(url: url)
        XCTAssertNil(history?.error)
        XCTAssertEqual(history?.items.count, 4)
        XCTAssertEqual(history?.items.filter { $0.payload == "legacy duplicate" }.count, 2)
        XCTAssertTrue(try XCTUnwrap(history).record("legacy duplicate"))
        XCTAssertEqual(history?.items.count, 4)
        XCTAssertTrue(try XCTUnwrap(history).record("new value"))
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: try XCTUnwrap(history).exportData()) as? [String: Any])
        let rows = try XCTUnwrap(json["records"] as? [[String: Any]])
        XCTAssertEqual(rows.count, 5)
        XCTAssertEqual(rows.filter { ($0["payload"] as? String) == "legacy duplicate" }.count, 2)
        XCTAssertEqual(rows.filter { $0["payload"] is NSNull }.count, 1)
        XCTAssertEqual(rows.compactMap { $0["createdAtUnixSeconds"] as? Double }.suffix(3), [1431993600,1431993500,0])
        history = nil
        let reopened = MacHistory(url: url)
        XCTAssertEqual(reopened.items.count, 5)
        let new = try XCTUnwrap(reopened.items.first(where: { $0.payload == "new value" }))
        reopened.delete(new)
        XCTAssertEqual(MacHistory(url: url).items.count, 4)
    }

    func testUnreadableStoreRemainsIntactAndCopyStillWorks() throws {
        let url = try directory().appendingPathComponent("coredata.sqlite")
        let data = Data("not a sqlite database - preserve me".utf8)
        try data.write(to: url)
        let history = MacHistory(url: url)
        XCTAssertNotNil(history.error)
        XCTAssertThrowsError(try history.exportData())
        let workspace = MacWorkspace(history: history)
        workspace.accept(["Safe copy after storage error"])
        XCTAssertEqual(workspace.payload, "Safe copy after storage error")
        let original = NSPasteboard.general.string(forType: .string)
        defer { NSPasteboard.general.clearContents(); if let original { NSPasteboard.general.setString(original, forType: .string) } }
        workspace.copy()
        XCTAssertEqual(NSPasteboard.general.string(forType: .string), workspace.payload)
        XCTAssertEqual(try Data(contentsOf: url), data)
        XCTAssertNotNil(history.error)
    }

    func testCancelledDecodeCannotReplaceSelection() async throws {
        let history = MacHistory(url: try directory().appendingPathComponent("coredata.sqlite"))
        let workspace = MacWorkspace(history: history)
        let data = try XCTUnwrap(QRImageCodec.png(payload: "stale"))
        workspace.read(data: data)
        workspace.cancelRead()
        workspace.accept(["current"])
        try await Task.sleep(nanoseconds: 500_000_000)
        XCTAssertEqual(workspace.payload, "current")
        XCTAssertEqual(history.items.map(\.payload), ["current"])
        XCTAssertFalse(workspace.isReading)
    }

    func testCameraAbsenceIsExplicit() throws {
        let camera = MacCamera()
        print("Actual camera inventory:", camera.devices.map(\.localizedName))
        if camera.devices.isEmpty {
            camera.start(deviceID: nil)
            XCTAssertTrue(camera.status.contains("No camera"))
            XCTAssertFalse(camera.running)
        } else {
            throw XCTSkip("Physical camera absence cannot be asserted on this runner")
        }
    }
}
