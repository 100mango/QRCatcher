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
        // Native Vision XCTest explicitly reports manual screenshots unsupported.
        // The cloud script takes actual public simctl pixels at this checkpoint.
        let description = String(app.debugDescription.prefix(20000))
        let attachment = XCTAttachment(string: description); attachment.name = name + "-accessibility"; attachment.lifetime = .keepAlways; add(attachment)
        print("QRCATCHER_VISION_CAPTURE:" + name); fflush(stdout)
        Thread.sleep(forTimeInterval: 5)
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
