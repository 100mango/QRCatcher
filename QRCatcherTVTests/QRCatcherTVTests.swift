import XCTest
import Foundation
@testable import QRCatcherTV

@MainActor
final class QRCatcherTVTests: XCTestCase {
    private func settings() throws -> (UserDefaults, String) {
        let name = "QRCatcher.TV.Unit." + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        addTeardownBlock { defaults.removePersistentDomain(forName: name) }
        return (defaults, name)
    }
    func testIndependentQRDecodeAndExportReadback() throws {
        for (name, expected) in ["ascii":["https://example.com/qrcatcher?source=golden"],"unicode":["QRCatcher 你好 🌈 123"],"rotated":["QRCatcher 你好 🌈 123"],"invalid":[]] {
            let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: name, withExtension: "png"))
            XCTAssertEqual(try QRImageCodec.decode(data: Data(contentsOf: url)), expected)
            for value in expected { XCTAssertEqual(try QRImageCodec.decode(data: XCTUnwrap(QRImageCodec.png(payload: value))), [value]) }
        }
        XCTAssertNil(QRPayload.safeWebURL("https://name:secret@example.com"))
    }
    func testLocalTVHistoryPreservesOrderDatesDuplicatesAndReopens() throws {
        let (defaults, domain) = try settings()
        let key = "history"
        let date = Date(timeIntervalSince1970: 1431993600)
        let rows: [[String: Any]] = [
            ["id":UUID().uuidString,"payload":"duplicate","createdAt":date.timeIntervalSinceReferenceDate],
            ["id":UUID().uuidString,"payload":"duplicate","createdAt":date.addingTimeInterval(-10).timeIntervalSinceReferenceDate]
        ]
        defaults.set(try JSONSerialization.data(withJSONObject: ["version":1,"records":rows]), forKey: key)
        let history = TVHistory(defaults: defaults, domain: domain, key: key)
        XCTAssertNil(history.error); XCTAssertEqual(history.items.map(\.payload), ["duplicate","duplicate"])
        XCTAssertTrue(history.record(["duplicate","new text 你好"], sourceAssetIdentifier: "synthetic-local-photo"))
        let reopened = TVHistory(defaults: defaults, domain: domain, key: key)
        XCTAssertEqual(reopened.items.map(\.payload), ["new text 你好","duplicate","duplicate"])
        XCTAssertEqual(reopened.items.suffix(2).map(\.createdAt), [date,date.addingTimeInterval(-10)])
        reopened.delete(try XCTUnwrap(reopened.items.first))
        XCTAssertEqual(TVHistory(defaults: defaults, domain: domain, key: key).items.count, 2)
    }
    func testQuotaCountsOtherDefaultsAndNeverSilentlyEvictsOrPartiallySaves() throws {
        let (defaults, domain) = try settings(); let key = "history"
        let history = TVHistory(defaults: defaults, domain: domain, key: key)
        XCTAssertTrue(history.record(["preserve"], sourceAssetIdentifier: nil))
        let bytes = try XCTUnwrap(defaults.data(forKey: key))
        defaults.set(Data(count: 200 * 1024), forKey: "other-app-metadata")
        XCTAssertFalse(history.record(["would be a partial new record", String(repeating: "x", count: 100 * 1024)], sourceAssetIdentifier: nil))
        XCTAssertEqual(defaults.data(forKey: key), bytes)
        XCTAssertEqual(history.items.map(\.payload), ["preserve"])
        XCTAssertNotNil(history.error)
        defaults.removeObject(forKey: "other-app-metadata")
        XCTAssertTrue(history.record(["retry succeeds"], sourceAssetIdentifier: nil))
        XCTAssertEqual(TVHistory(defaults: defaults, domain: domain, key: key).items.count, 2)
    }
    func testUnreadableTVHistoryIsNotReplacedByNewScans() throws {
        let (defaults, domain) = try settings(); let sentinel = Data("retain this unreadable value".utf8)
        defaults.set(sentinel, forKey: "history")
        let history = TVHistory(defaults: defaults, domain: domain, key: "history")
        XCTAssertNotNil(history.error); XCTAssertFalse(history.record(["unsaved"], sourceAssetIdentifier: nil))
        XCTAssertEqual(defaults.data(forKey: "history"), sentinel)
    }
}
