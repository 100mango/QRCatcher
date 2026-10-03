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
    private func focusAndSelect(_ target: XCUIElement, root: XCUIElement? = nil, activate: Bool = true) {
        XCTAssertTrue(target.waitForExistence(timeout: 15))
        let scope = root ?? app!
        for _ in 0..<30 {
            if target.hasFocus { if activate { XCUIRemote.shared.press(.select) }; return }
            let focusedCell = scope.descendants(matching: .cell).matching(NSPredicate(format: "hasFocus == true")).firstMatch
            if focusedCell.exists, !target.identifier.isEmpty,
               focusedCell.buttons.count == 1, focusedCell.buttons[target.identifier].exists {
                // Native tvOS List reports focus on the cell that owns its one
                // button. Never infer an action from a multi-button cell.
                if activate { XCUIRemote.shared.press(.select) }; return
            }
            let focusedButton = scope.descendants(matching: .button).matching(NSPredicate(format: "hasFocus == true")).firstMatch
            let focused = focusedButton.exists ? focusedButton : scope.descendants(matching: .any).matching(NSPredicate(format: "hasFocus == true")).firstMatch
            if focused.exists {
                let destination = target.frame, origin = focused.frame
                if focused.label == target.label && abs(destination.midX-origin.midX) < 2 && abs(destination.midY-origin.midY) < 2 {
                    // tvOS can expose nested buttons with the same frame/title;
                    // activate the actual focused child of this exact control.
                    if activate { XCUIRemote.shared.press(.select) }; return
                }
                // The observed permission dialog starts at Select: above its
                // action row. Align rows before horizontal movement.
                if destination.minY >= origin.maxY - 1 { XCUIRemote.shared.press(.down) }
                else if destination.maxY <= origin.minY + 1 { XCUIRemote.shared.press(.up) }
                else { XCUIRemote.shared.press(destination.midX >= origin.midX ? .right : .left) }
            } else { XCUIRemote.shared.press(.down) }
        }
        if root != nil && target.label == "Allow All Photos" {
            print("QRCATCHER_TV_EXACT_PERMISSION_FOCUS_BLOCKED"); fflush(stdout)
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
            do { try app.performAccessibilityAudit(for: .all) { issue in print("TV_ACCESSIBILITY_ISSUE", issue.compactDescription, issue.detailedDescription, issue.element?.debugDescription ?? "no issue element"); return false } }
            catch { XCTFail("TV accessibility audit failed: \(error)") }
        }
        guard let data = XCUIScreen.main.screenshot().image.jpegData(compressionQuality: 0.45) else { return }
        XCTAssertLessThanOrEqual(data.count, 800 * 1024)
        let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.jpeg")
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
    func testActualPhotosDecodeExportVerificationAndOfflineReopen() { realPhotosWorkflow(expectPrompt: true) }
    func testExplicitlyPreconditionedPhotosDecodeExportAndReopen() {
        print("PRECONDITIONED_SIMULATOR_PHOTOS_GRANTED: this does not qualify system prompt interaction")
        realPhotosWorkflow(expectPrompt: false)
    }
    func testExplicitlyRevokedPhotosRecovery() {
        print("PRECONDITIONED_SIMULATOR_PHOTOS_REVOKED: separate from real prompt denial interaction")
        focusAndSelect(app.buttons["tv.photos"])
        let explanation = app.staticTexts["Photos access is unavailable. You can change access in Settings, then choose Retry."]
        XCTAssertTrue(explanation.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertFalse(app.buttons["tv.asset.0"].exists)
        capture("tv-revoked-photos")
        XCUIRemote.shared.press(.menu)
        XCTAssertTrue(app.buttons["tv.photos"].waitForExistence(timeout: 10))
    }
    private func realPhotosWorkflow(expectPrompt: Bool) {
        focusAndSelect(app.buttons["tv.photos"])
        // The actual tvOS 27 permission dialog belongs to the system app, not
        // the target app's accessibility subtree. Exact title/button only.
        if expectPrompt { respondToExactPhotosPermissionIfPresent() }
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
        capture("tv-history-list")
        focusAndSelect(record, activate: false); capture("tv-history-focused-record")
        let remove = app.buttons["tv.deleteRecord"].firstMatch
        focusAndSelect(remove, activate: false); capture("tv-history-focused-delete")
        focusAndSelect(record)
        XCTAssertEqual(app.staticTexts["tv.payload"].label, "QRCatcher 你好 🌈 123")
        capture("tv-reopened-history")
        focusAndSelect(app.buttons["tv.privacy"])
        XCTAssertTrue(app.staticTexts["privacy.offlineBody"].waitForExistence(timeout: 10))
        capture("tv-offline-policy")
        XCUIRemote.shared.press(.menu)
        XCTAssertTrue(app.buttons["tv.photos"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["tv.privacy"].hasFocus, "Menu must return focus to the presenting Privacy control")
        app.terminate(); app.launchArguments = ["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN"]; app.launch()
        focusAndSelect(app.buttons["tv.history"])
        let chineseRecord = app.buttons["tv.record"].firstMatch
        XCTAssertTrue(chineseRecord.waitForExistence(timeout: 15)); focusAndSelect(chineseRecord)
        XCTAssertEqual(app.staticTexts["tv.payload"].label, "QRCatcher 你好 🌈 123")
        XCTAssertEqual(app.buttons["tv.photos"].label, "照片")
        capture("tv-chinese-result")
    }
}
