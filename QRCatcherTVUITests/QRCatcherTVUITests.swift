import XCTest
import UIKit

@MainActor
final class QRCatcherTVUITests: XCTestCase {
    private var app: XCUIApplication!
    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["-AppleLanguages","(en)","-AppleLocale","en_US"]
        app.launchEnvironment["QRCATCHER_TV_TEST_STORE"] = UUID().uuidString
        addUIInterruptionMonitor(withDescription: "Explicit Photos request") { alert in
            let text = alert.debugDescription
            guard text.localizedCaseInsensitiveContains("Photos"), text.contains("QRCatcher") else { return false }
            let allow = alert.buttons["Allow Full Access"].exists ? alert.buttons["Allow Full Access"] : alert.buttons["Allow"]
            guard allow.exists else { return false }
            self.focusAndSelect(allow, root: alert)
            return true
        }
        app.launch()
    }
    override func tearDownWithError() throws {
        if (testRun?.failureCount ?? 0) > 0 { print("TV_FAILURE_UI:",app.debugDescription); capture("tv-failure") }
        app.terminate()
    }
    private func focusAndSelect(_ target: XCUIElement, root: XCUIElement? = nil) {
        XCTAssertTrue(target.waitForExistence(timeout: 15))
        let scope = root ?? app!
        for _ in 0..<30 {
            if target.hasFocus { XCUIRemote.shared.press(.select); return }
            let focused = scope.descendants(matching: .any).matching(NSPredicate(format: "hasFocus == true")).firstMatch
            if focused.exists {
                let dx = target.frame.midX - focused.frame.midX, dy = target.frame.midY - focused.frame.midY
                XCUIRemote.shared.press(abs(dx) > abs(dy) ? (dx >= 0 ? .right : .left) : (dy >= 0 ? .down : .up))
            } else { XCUIRemote.shared.press(.down) }
        }
        XCTFail("Remote focus could not reach the actual control: \(target.debugDescription)")
    }
    private func capture(_ name: String) {
        guard let data = XCUIScreen.main.screenshot().image.jpegData(compressionQuality: 0.45) else { return }
        XCTAssertLessThanOrEqual(data.count, 800 * 1024)
        let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.jpeg")
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
    func testActualPhotosDecodeExportVerificationAndOfflineReopen() {
        focusAndSelect(app.buttons["tv.photos"])
        // A directional event lets XCTest inspect an expected system permission
        // interruption without blindly activating any alert or source control.
        XCUIRemote.shared.press(.down)
        let photo = app.buttons["tv.asset.0"]
        XCTAssertTrue(photo.waitForExistence(timeout: 20), app.debugDescription)
        focusAndSelect(photo)
        let payload = app.staticTexts["tv.payload"]
        XCTAssertTrue(payload.waitForExistence(timeout: 20), app.debugDescription)
        XCTAssertEqual(payload.label, "QRCatcher 你好 🌈 123")
        capture("tv-real-photo-result")
        focusAndSelect(app.buttons["tv.export"])
        let saved = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", "Saved to Photos and verified"), object: app.staticTexts["tv.status"])
        XCTAssertEqual(XCTWaiter.wait(for: [saved], timeout: 30), .completed)
        capture("tv-verified-photos-output")
        app.terminate(); app.launch()
        focusAndSelect(app.buttons["tv.history"])
        let record = app.buttons["tv.record"].firstMatch
        XCTAssertTrue(record.waitForExistence(timeout: 15))
        focusAndSelect(record)
        XCTAssertEqual(app.staticTexts["tv.payload"].label, "QRCatcher 你好 🌈 123")
        capture("tv-reopened-history")
        focusAndSelect(app.buttons["tv.privacy"])
        XCTAssertTrue(app.staticTexts["privacy.offlineBody"].waitForExistence(timeout: 10))
        XCUIRemote.shared.press(.menu)
        XCTAssertTrue(app.buttons["tv.photos"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["tv.privacy"].hasFocus, "Menu must return focus to the presenting Privacy control")
    }
}
