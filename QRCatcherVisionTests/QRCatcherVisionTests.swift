import XCTest
import CoreData
@testable import QRCatcherVision

@MainActor
final class QRCatcherVisionTests: XCTestCase {
    private func storeURL() throws -> URL {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: folder) }
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
        let history = MacHistory(url: url)
        let session = VisionReadSession(history: history)
        let fixture = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "unicode", withExtension: "png"))
        session.read(url: fixture)
        for _ in 0..<80 { if session.payload != nil { break }; try await Task.sleep(nanoseconds: 100_000_000) }
        XCTAssertEqual(session.payload, "QRCatcher 你好 🌈 123")
        XCTAssertEqual(MacHistory(url: url).items.first?.payload, session.payload)
        let export = try XCTUnwrap(JSONSerialization.jsonObject(with: history.exportData()) as? [String:Any])
        XCTAssertEqual((export["records"] as? [[String:Any]])?.first?["payload"] as? String, session.payload)
    }
    func testCancellationAndSafeActions() async throws {
        let history = MacHistory(url: try storeURL())
        let session = VisionReadSession(history: history)
        session.read(data: try XCTUnwrap(QRImageCodec.png(payload: "stale")))
        session.cancel(); session.accept(["current"])
        try await Task.sleep(nanoseconds: 500_000_000)
        XCTAssertEqual(session.payload, "current")
        XCTAssertEqual(history.items.map(\.payload), ["current"])
        for value in ["javascript:alert(1)","file:///etc/passwd","https://user:secret@example.com","plain text"] { XCTAssertNil(QRPayload.safeWebURL(value)) }
    }
    func testUnreadableStoreNeverErasesBytes() throws {
        let url = try storeURL(); let sentinel = Data("Preserve unreadable history".utf8); try sentinel.write(to: url)
        let history = MacHistory(url: url)
        XCTAssertNotNil(history.error); XCTAssertFalse(history.record("unsaved"))
        XCTAssertEqual(try Data(contentsOf: url), sentinel)
        XCTAssertThrowsError(try history.exportData())
    }
}
