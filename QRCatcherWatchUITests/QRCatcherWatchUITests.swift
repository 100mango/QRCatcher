import XCTest

@MainActor final class QRCatcherWatchUITests: XCTestCase {
    private var app: XCUIApplication!
    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication(); app.launchEnvironment["QRCATCHER_WATCH_STORE"] = UUID().uuidString
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]; app.launch()
    }
    override func tearDownWithError() throws { if (testRun?.failureCount ?? 0) > 0 { print(app.debugDescription); capture("watch-failure") }; app.terminate() }
    private func capture(_ name: String) {
        if name != "watch-failure" && name != "watch-system-picker-unavailable" {
            do { try app.performAccessibilityAudit(for: .all) { issue in print("WATCH_ACCESSIBILITY_ISSUE", issue.compactDescription); return false } }
            catch { XCTFail("Watch accessibility audit failed: \(error)") }
        }
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot()); attachment.name = name; attachment.lifetime = .keepAlways; add(attachment) }
    func testNativeEmptyCollectionAndOfflinePolicy() {
        XCTAssertTrue(app.buttons["watch.photos"].waitForExistence(timeout: 20))
        XCTAssertFalse(app.staticTexts["watch.store-error"].exists)
        capture("watch-empty")
        let policy = app.buttons["watch.privacy"]
        if !policy.isHittable { app.swipeUp() }
        XCTAssertTrue(policy.waitForExistence(timeout: 5)); policy.tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "process photos")).firstMatch.waitForExistence(timeout: 5))
        capture("watch-offline-policy")
    }
    func testSystemPhotosPickerSimulatorUnavailableAndClose() {
        XCTAssertTrue(app.buttons["watch.photos"].waitForExistence(timeout: 20)); app.buttons["watch.photos"].tap()
        let unavailable = app.staticTexts["Unable to Load Photos in Simulator"]
        XCTAssertTrue(unavailable.waitForExistence(timeout: 20), app.debugDescription)
        XCTAssertTrue(app.staticTexts["You need to use an Apple Watch."].exists)
        capture("watch-system-picker-unavailable")
        app.buttons["Close"].tap()
        XCTAssertTrue(app.buttons["watch.photos"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["watch.record"].exists)
    }
    func testFixtureFedOfflineResultSourceImageAndRelaunch() {
        app.terminate(); app.launchEnvironment["QRCATCHER_WATCH_STORE"] = "81F3B791-5049-4ED7-B88E-9684DA76DDB8"; app.launch()
        // Hosted test prepared this source photo using the genuine Watch decoder.
        // This checks offline UI/persistence, not system Photos selection.
        let record = app.buttons["watch.record"].firstMatch
        XCTAssertTrue(record.waitForExistence(timeout: 20), app.debugDescription); record.tap()
        let payload = app.staticTexts["watch.payload"]
        if !payload.isHittable { app.swipeUp() }
        XCTAssertTrue(payload.waitForExistence(timeout: 10)); XCTAssertEqual(payload.label, "QRCatcher 你好 🌈 123")
        capture("watch-fixture-offline-result")
        app.terminate(); app.launch()
        XCTAssertTrue(record.waitForExistence(timeout: 15)); record.tap(); app.swipeUp()
        XCTAssertEqual(app.staticTexts["watch.payload"].label, "QRCatcher 你好 🌈 123"); capture("watch-reopened-qr")
    }
}
