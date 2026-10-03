import XCTest
import UIKit

@MainActor
final class QRCatcherVisionUITests: XCTestCase {
    private var app: XCUIApplication!
    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launchEnvironment["QRCATCHER_TEST_STORE_NAME"] = UUID().uuidString
        app.launch()
    }
    override func tearDownWithError() throws {
        if (testRun?.failureCount ?? 0) > 0 { print(app.debugDescription); capture("vision-failure") }
        app.terminate()
    }
    private func capture(_ name: String) {
        if name != "vision-failure" {
            do { try app.performAccessibilityAudit(for: .all) { issue in print("VISION_ACCESSIBILITY_ISSUE", issue.compactDescription, issue.detailedDescription, issue.element?.debugDescription ?? "no issue element"); return false } }
            catch { XCTFail("VISION accessibility audit failed: \(error)") }
        }
        // Native Vision XCTest explicitly reports manual screenshots unsupported.
        // The cloud script takes actual public simctl pixels at this checkpoint.
        let description = String(app.debugDescription.prefix(20000))
        let attachment = XCTAttachment(string: description); attachment.name = name + "-accessibility"; attachment.lifetime = .keepAlways; add(attachment)
        let id = UUID().uuidString
        let request = FileManager.default.temporaryDirectory.appendingPathComponent("QRCatcher-capture-" + id + ".json")
        let ack = request.deletingPathExtension().appendingPathExtension("ack")
        do {
            let descriptor = try JSONSerialization.data(withJSONObject: ["id": id, "name": name])
            try descriptor.write(to: request, options: .atomic)
            print("QRCATCHER_VISION_CAPTURE_REQUEST:" + id); fflush(stdout)
            let deadline = Date().addingTimeInterval(45)
            while Date() < deadline && !FileManager.default.fileExists(atPath: ack.path) { Thread.sleep(forTimeInterval: 0.2) }
            let result = try JSONSerialization.jsonObject(with: Data(contentsOf: ack)) as? [String: Any]
            XCTAssertEqual(result?["id"] as? String, id)
            XCTAssertEqual(result?["success"] as? Bool, true, "Held simulator checkpoint failed: \(String(describing: result))")
        } catch { XCTFail("Held simulator capture acknowledgement: \(error)") }
        try? FileManager.default.removeItem(at: request); try? FileManager.default.removeItem(at: ack)
    }
    func testRealPhotosImportCopyAndReopen() {
        XCTAssertTrue(app.buttons["vision.photos"].waitForExistence(timeout: 20))
        app.buttons["vision.photos"].tap()
        let asset = app.images["PXGGridLayout-Info"].firstMatch
        XCTAssertTrue(asset.waitForExistence(timeout: 20), app.debugDescription)
        asset.tap()
        XCTAssertTrue(app.staticTexts["vision.payload"].waitForExistence(timeout: 20), app.debugDescription)
        XCTAssertEqual(app.staticTexts["vision.payload"].label, "QRCatcher 你好 🌈 123")
        XCTAssertFalse(app.buttons["vision.openWebsite"].exists)
        app.buttons["vision.copy"].tap()
        XCTAssertEqual(app.staticTexts["vision.status"].label, "Result copied")
        capture("vision-imported-qr")
        app.terminate(); app.launch()
        let record = app.staticTexts["QRCatcher 你好 🌈 123"]
        XCTAssertTrue(record.waitForExistence(timeout: 15)); record.tap()
        XCTAssertTrue(app.buttons["vision.exportQR"].waitForExistence(timeout: 5))
        capture("vision-reopened-history")
    }
}
