import XCTest
import CoreData
import Combine
@testable import QRCatcherVision

@MainActor
final class QRCatcherVisionTests: QRManagedStoreTestCase {
    private func storeURL() throws -> URL {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        cleanupLater(folder)
        return folder.appendingPathComponent("coredata.sqlite")
    }
    func testIndependentGoldenDecodeAndPNGReadback() throws {
        for (name, values) in ["ascii":["https://example.com/qrcatcher?source=golden"], "unicode":["QRCatcher 你好 🌈 123"], "rotated":["QRCatcher 你好 🌈 123"], "invalid":[]] {
            let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: name, withExtension: "png"))
            XCTAssertEqual(try QRImageCodec.decode(data: Data(contentsOf: url)), values)
            for value in values { XCTAssertEqual(try QRImageCodec.decode(data: XCTUnwrap(QRImageCodec.png(payload: value))), [value]) }
        }
    }
    func testActualReadPersistsAndReopens() async throws {
        let url = try storeURL()
        let history = makeHistory(url: url)
        let session = VisionReadSession(history: history)
        let fixture = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "unicode", withExtension: "png"))
        let started = ContinuousClock.now
        session.read(url: fixture)
        defer { session.cancel() }
        let finished = expectation(description: "Actual asynchronous image read completed")
        // Subscribe after read() synchronously marks the session busy. Completion
        // is a lifecycle event, not an assumed number of short scheduler sleeps.
        let observation = session.$isReading.dropFirst().filter { !$0 }.prefix(1).sink { _ in finished.fulfill() }
        defer { observation.cancel() }
        let outcome = await XCTWaiter.fulfillment(of: [finished], timeout: 60)
        print("VISION_ACTUAL_READ_COMPLETION", "elapsed", started.duration(to: .now), "wait", outcome.rawValue,
              "isReading", session.isReading, "status", session.status, "error", session.error ?? "none")
        XCTAssertEqual(outcome, .completed)
        XCTAssertFalse(session.isReading)
        XCTAssertNil(session.error)
        let payload = try XCTUnwrap(session.payload, "Actual read must produce a result before persistence is checked")
        XCTAssertEqual(payload, "QRCatcher 你好 🌈 123")
        XCTAssertEqual(makeHistory(url: url).items.first?.payload, "QRCatcher 你好 🌈 123")
        let export = try XCTUnwrap(JSONSerialization.jsonObject(with: history.exportData()) as? [String:Any])
        XCTAssertEqual((export["records"] as? [[String:Any]])?.first?["payload"] as? String, "QRCatcher 你好 🌈 123")
    }
    func testCancellationAndSafeActions() async throws {
        let history = makeHistory(url: try storeURL())
        let session = VisionReadSession(history: history)
        session.read(data: try XCTUnwrap(QRImageCodec.png(payload: "stale")))
        session.cancel(); session.accept(["current"])
        try await Task.sleep(nanoseconds: 500_000_000)
        XCTAssertEqual(session.payload, "current")
        XCTAssertEqual(history.items.map(\.payload), ["current"])
        for value in ["javascript:alert(1)","file:///etc/passwd","https://user:secret@example.com","plain text"] { XCTAssertNil(QRPayload.safeWebURL(value)) }
    }
    func testOversizedProviderFileKeepsPreviousResultAndRejectsSymlink() throws {
        let store = try storeURL(), folder = store.deletingLastPathComponent()
        let history = makeHistory(url: store), session = VisionReadSession(history: history)
        session.accept(["existing result"])
        let large = folder.appendingPathComponent("oversized-photo.png")
        FileManager.default.createFile(atPath: large.path, contents: Data())
        let handle = try FileHandle(forWritingTo: large); try handle.truncate(atOffset: UInt64(QRBoundedPhotoFile.maximumBytes + 1)); try handle.close()
        let token = session.beginExternalLoad()
        do { _ = try QRBoundedPhotoFile.read(large); XCTFail("Provider bytes must be bounded before materialization") }
        catch { session.completeExternalLoad(token, data: nil, error: error) }
        XCTAssertEqual(session.payload, "existing result"); XCTAssertEqual(history.items.map(\.payload), ["existing result"])
        let link = folder.appendingPathComponent("provider-link.png"); try FileManager.default.createSymbolicLink(at: link, withDestinationURL: large)
        XCTAssertThrowsError(try QRBoundedPhotoFile.read(link))
    }
    func testSelectedFileFailureAndCancellationPreservePreviousResult() async throws {
        let store = try storeURL(), history = makeHistory(url: store), session = VisionReadSession(history: history)
        session.accept(["keep this selection"])
        let file = store.deletingLastPathComponent().appendingPathComponent("oversized.png")
        FileManager.default.createFile(atPath: file.path, contents: Data())
        let handle = try FileHandle(forWritingTo: file); try handle.truncate(atOffset: UInt64(QRBoundedPhotoFile.maximumBytes + 1)); try handle.close()
        session.read(url: file)
        for _ in 0..<100 where session.isReading { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertFalse(session.isReading); XCTAssertNotNil(session.error)
        XCTAssertEqual(session.payload, "keep this selection"); XCTAssertEqual(session.history.items.map(\.payload), ["keep this selection"])
        session.read(url: file); session.cancel()
        try await Task.sleep(nanoseconds: 20_000_000)
        XCTAssertEqual(session.payload, "keep this selection"); XCTAssertEqual(session.history.items.count, 1)
    }

    func testProviderReadCancellationStopsBeforeRemainingChunks() throws {
        let file = try storeURL().deletingLastPathComponent().appendingPathComponent("provider.png")
        try Data(repeating: 0x20, count: 256 * 1024).write(to: file)
        let token = QRImportCancellation(); var checks = 0
        do {
            _ = try QRBoundedPhotoFile.read(file, isCancelled: { checks += 1; if checks == 3 { token.cancel() }; return token.isCancelled })
            XCTFail("Cancellation must interrupt the bounded provider read")
        } catch { XCTAssertTrue(error is CancellationError) }
        XCTAssertEqual(checks, 3)
    }
    func testRapidHistorySelectionLastIntentClearAndNewImport() async throws {
        let history = makeHistory(url: try storeURL())
        for value in ["A","B","C"] { XCTAssertTrue(history.record(value)) }
        let session = VisionReadSession(history: history)
        let ids = Dictionary(uniqueKeysWithValues: history.items.map { ($0.text, $0.id) })
        session.queueSelection(ids["A"]); session.queueSelection(ids["B"]); session.queueSelection(ids["C"])
        try await Task.sleep(nanoseconds: 20_000_000)
        XCTAssertEqual(session.payload, "C"); XCTAssertEqual(history.items.count, 3)
        session.queueSelection(ids["A"]); session.queueSelection(nil)
        try await Task.sleep(nanoseconds: 20_000_000)
        XCTAssertNil(session.selection); XCTAssertEqual(session.payload, "C")
        session.queueSelection(ids["A"]); session.accept(["new imported result"])
        try await Task.sleep(nanoseconds: 20_000_000)
        XCTAssertEqual(session.payload, "new imported result"); XCTAssertEqual(history.items.count, 4)
    }
    func testUnreadableStoreNeverErasesBytes() throws {
        let url = try storeURL(); let sentinel = Data("Preserve unreadable history".utf8); try sentinel.write(to: url)
        let history = makeHistory(url: url)
        XCTAssertNotNil(history.error); XCTAssertFalse(history.record("unsaved"))
        XCTAssertEqual(try Data(contentsOf: url), sentinel)
        XCTAssertThrowsError(try history.exportData())
    }
}
