import XCTest
import Darwin
import CoreGraphics

@MainActor final class QRCatcherWatchUITests: XCTestCase {
    private var app: XCUIApplication!
    private var interruptionGuard: NSObjectProtocol?
    override func setUpWithError() throws {
        continueAfterFailure = false
        // Installed before any app/system-app launch and retained through teardown.
        interruptionGuard = addUIInterruptionMonitor(withDescription: "Stop before every unexpected system interruption") { alert in
            QRStopForUnexpectedInterruption(alert)
        }
        app = XCUIApplication(); app.launchEnvironment["QRCATCHER_WATCH_STORE"] = UUID().uuidString
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]; app.launch()
    }
    override func tearDownWithError() throws {
        defer { if let interruptionGuard { removeUIInterruptionMonitor(interruptionGuard) } }
        if (testRun?.failureCount ?? 0) > 0 { print(app.debugDescription); capture("watch-failure") }
        app.terminate()
    }
    private func reveal(_ target: XCUIElement) {
        XCTAssertTrue(target.waitForExistence(timeout: 10), app.debugDescription)
        let window = app.frame
        let top = window.minY + 44, bottom = window.maxY - 12
        for attempt in 0..<16 {
            let frame = target.frame
            if target.isHittable && frame.height > 0 && frame.minY >= top && frame.maxY <= bottom { return }
            // A fixed fast 45-point release oscillated past the payload after a
            // full swipe in run 37176649273. Move toward the measured overflow
            // and hold at the endpoint so scroll momentum cannot fling it away.
            let above = frame.minY < top
            let overflow = above ? top - frame.minY : frame.maxY - bottom
            let movement = (above ? CGFloat(1) : -1) * min(40, max(8, (overflow + 4) * 0.5))
            print("WATCH_REVEAL_FRAME", target.identifier, attempt, frame, "movement", movement)
            // The compact preview occupies the center of the screen. Starting
            // below it when revealing later content keeps this gesture in the
            // outer record scroller, rather than the nested image pan viewport.
            let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: above ? 0.65 : 0.9))
            start.press(forDuration: 0.05, thenDragTo: start.withOffset(CGVector(dx: 0, dy: movement)),
                        withVelocity: .slow, thenHoldForDuration: 0.2)
        }
        XCTFail("Actual Watch target is not fully framed: \(target.debugDescription)")
    }
    private func capture(_ name: String, revealing target: XCUIElement? = nil) {
        if let target { reveal(target) }
        // The audit traverses and scrolls the screen. Save the asserted state
        // before it runs; never name the later bottom-of-record frame a result.
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
        if #available(watchOS 10.0, *), name != "watch-failure" && name != "watch-system-picker-unavailable" {
            do { try app.performAccessibilityAudit(for: .all) { issue in print("WATCH_ACCESSIBILITY_ISSUE", issue.compactDescription, issue.detailedDescription, issue.element?.debugDescription ?? "no issue element"); return false } }
            catch { XCTFail("Watch accessibility audit failed: \(error)") }
        }
    }
    func testNativeEmptyCollectionAndOfflinePolicy() {
        XCTAssertTrue(app.buttons["watch.photos"].waitForExistence(timeout: 20))
        XCTAssertFalse(app.staticTexts["watch.store-error"].exists)
        capture("watch-empty", revealing: app.buttons["watch.photos"])
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
    func testSyntheticJournalRecoveryAcrossActualAppRelaunch() {
        app.terminate(); app.launchEnvironment["QRCATCHER_WATCH_STORE"] = "49F5E6A7-20ED-4BD9-BF4E-C4B44F652F21"; app.launch()
        print("WATCH_SYNTHETIC_JOURNAL_RECOVERY: actual separate app process and persistence, not WC file delivery")
        let record = app.buttons["watch.record"].firstMatch
        XCTAssertTrue(record.waitForExistence(timeout: 20)); record.tap(); reveal(app.staticTexts["watch.payload"])
        XCTAssertEqual(app.staticTexts["watch.payload"].label, "QRCatcher 你好 🌈 123")
        XCTAssertEqual(app.staticTexts["watch.phone-state"].label, "Completed")
        capture("watch-recovered-journal", revealing: app.staticTexts["watch.payload"])
        app.terminate(); app.launch()
        XCTAssertTrue(record.waitForExistence(timeout: 15)); record.tap(); reveal(app.staticTexts["watch.payload"])
        XCTAssertEqual(app.staticTexts["watch.payload"].label, "QRCatcher 你好 🌈 123")
        XCTAssertEqual(app.staticTexts["watch.phone-state"].label, "Completed")
    }
    func testFixtureFedOfflineResultSourceImageAndRelaunch() {
        app.terminate(); app.launchEnvironment["QRCATCHER_WATCH_STORE"] = "81F3B791-5049-4ED7-B88E-9684DA76DDB8"; app.launch()
        // Hosted test prepared this source photo using the genuine Watch decoder.
        // This checks offline UI/persistence, not system Photos selection.
        let record = app.buttons["watch.record"].firstMatch
        XCTAssertTrue(record.waitForExistence(timeout: 20), app.debugDescription); record.tap()
        let sourceImage = app.images["watch.source-image"]
        capture("watch-saved-preview", revealing: sourceImage)
        let payload = app.staticTexts["watch.payload"]
        reveal(payload)
        XCTAssertTrue(payload.waitForExistence(timeout: 10)); XCTAssertEqual(payload.label, "QRCatcher 你好 🌈 123")
        capture("watch-fixture-offline-result", revealing: payload)
        app.terminate(); app.launch()
        XCTAssertTrue(record.waitForExistence(timeout: 15)); record.tap()
        XCTAssertEqual(app.staticTexts["watch.payload"].label, "QRCatcher 你好 🌈 123"); capture("watch-reopened-qr", revealing: app.staticTexts["watch.payload"])
    }
}

// Test-runner-only stop. Returning false or throwing an XCTest assertion here
// would permit the default interruption handler to approve an unknown prompt.
@MainActor private func QRStopForUnexpectedInterruption(_ alert: XCUIElement) -> Never {
    fputs("QRCATCHER_UNEXPECTED_INTERRUPTION_ABORT_BEFORE_UI_ACTION\n", stderr); fflush(stderr)
    // Do not query AX or record a throwable assertion before this stop.
    abort()
}
