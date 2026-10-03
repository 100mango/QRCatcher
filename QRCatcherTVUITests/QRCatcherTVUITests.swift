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
    private func respondToExactPhotosPermissionIfPresent() {
        let system = XCUIApplication(bundleIdentifier: "com.apple.PineBoard")
        let allow = system.buttons["Allow All Photos"].firstMatch
        if allow.waitForExistence(timeout: 8) {
            let title = system.staticTexts.matching(NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@", "QRCatcher", "photo library")).firstMatch
            XCTAssertTrue(title.exists, "Only QRCatcher's explicit Photos request may be accepted: \(system.debugDescription)")
            print("TV_OBSERVED_SYSTEM_PHOTOS_DIALOG:", system.debugDescription)
            focusAndSelect(allow, root: system)
        } else {
            print("TV_PHOTOS_PERMISSION_SYSTEM_UI:", system.debugDescription)
        }
    }
    private func capture(_ name: String) {
        if name != "tv-failure" {
            do { try app.performAccessibilityAudit(for: .all) { issue in print("TV_ACCESSIBILITY_ISSUE", issue.compactDescription); return false } }
            catch { XCTFail("TV accessibility audit failed: \(error)") }
        }
        guard let data = XCUIScreen.main.screenshot().image.jpegData(compressionQuality: 0.45) else { return }
        XCTAssertLessThanOrEqual(data.count, 800 * 1024)
        let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.jpeg")
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
    func testActualPhotosDecodeExportVerificationAndOfflineReopen() {
        focusAndSelect(app.buttons["tv.photos"])
        // The actual tvOS 27 permission dialog belongs to the system app, not
        // the target app's accessibility subtree. Exact title/button only.
        respondToExactPhotosPermissionIfPresent()
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
