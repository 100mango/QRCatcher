import XCTest
import Darwin
import UIKit

@MainActor
final class QRCatcherVisionUITests: XCTestCase {
    private var app: XCUIApplication!
    private var interruptionGuard: NSObjectProtocol?
    override func setUpWithError() throws {
        continueAfterFailure = false
        // Installed before any app/system-app launch and retained through teardown.
        interruptionGuard = addUIInterruptionMonitor(withDescription: "Stop before every unexpected system interruption") { alert in
            QRStopForUnexpectedInterruption(alert)
        }
        app = XCUIApplication()
        let chinese = name.contains("testChineseEmptyPhotosResultAndOfflinePolicy")
        app.launchArguments = chinese ? ["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN"] : ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launchEnvironment["QRCATCHER_TEST_STORE_NAME"] = UUID().uuidString
        app.launch()
    }
    override func tearDownWithError() throws {
        defer { if let interruptionGuard { removeUIInterruptionMonitor(interruptionGuard) } }

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
            let descriptor = try JSONSerialization.data(withJSONObject: ["id": id, "name": name, "test_store": app.launchEnvironment["QRCATCHER_TEST_STORE_NAME"] ?? ""])
            try descriptor.write(to: request, options: .atomic)
            print("QRCATCHER_VISION_CAPTURE_REQUEST:" + id); fflush(stdout)
            let deadline = Date().addingTimeInterval(100)
            while Date() < deadline && !FileManager.default.fileExists(atPath: ack.path) { Thread.sleep(forTimeInterval: 0.2) }
            let result = try JSONSerialization.jsonObject(with: Data(contentsOf: ack)) as? [String: Any]
            if name == "vision-failure" {
                print("VISION_FAILURE_CAPTURE_DIAGNOSTIC", String(describing: result))
            } else {
                XCTAssertEqual(result?["id"] as? String, id)
                XCTAssertEqual(result?["success"] as? Bool, true, "Held simulator checkpoint failed: \(String(describing: result))")
            }
        } catch {
            if name == "vision-failure" { print("VISION_FAILURE_CAPTURE_DIAGNOSTIC", error) }
            else { XCTFail("Held simulator capture acknowledgement: \(error)") }
        }
        try? FileManager.default.removeItem(at: request); try? FileManager.default.removeItem(at: ack)
    }
    private func saveUsingSystemFileExporter(_ button: String, name: String, checkpoint: String) {
        app.buttons[button].tap()
        // These identifiers were observed in the native SDK 27 document picker.
        let filename = app.textFields["DOCPicker.filenameTextField"]
        XCTAssertTrue(filename.waitForExistence(timeout: 20), app.debugDescription)
        filename.tap()
        if let value = filename.value as? String, !value.isEmpty { filename.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: value.count)) }
        filename.typeText(name)
        let save = app.buttons["DOCPicker.actionButton"]
        XCTAssertTrue(save.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(save.isEnabled, app.debugDescription); save.tap()
        let finished = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", "Export completed"), object: app.staticTexts["vision.status"])
        XCTAssertEqual(XCTWaiter.wait(for: [finished], timeout: 20), .completed, app.debugDescription)
        capture(checkpoint) // Host independently verifies bytes read from the saved URL.
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
        saveUsingSystemFileExporter("vision.exportQR", name: "QRCatcher Synthetic QR", checkpoint: "vision-exported-qr")
        // Copy resets the status, so a prior successful save cannot satisfy the
        // second completion assertion before that system exporter actually ends.
        app.buttons["vision.copy"].tap()
        saveUsingSystemFileExporter("vision.exportHistory", name: "QRCatcher Synthetic History", checkpoint: "vision-exported-history")
    }

    private func visibleFileItem(_ name: String) -> XCUIElement? {
        let identity = NSPredicate(format: "label == %@ OR identifier == %@ OR label BEGINSWITH %@", name, name, name + ",")
        for query in [app.cells, app.buttons, app.staticTexts] {
            let item = query.matching(identity).firstMatch
            if item.exists && item.isHittable { return item }
        }
        return nil
    }
    private func selectFileItem(_ name: String) {
        var item: XCUIElement?
        for _ in 0..<20 where item == nil { item = visibleFileItem(name); if item == nil { Thread.sleep(forTimeInterval: 0.5) } }
        guard let item else { XCTFail("Missing actual Files item \(name): \(app.debugDescription)"); return }
        item.tap()
    }
    func testRealFilesImportAndReopen() {
        XCTAssertTrue(app.buttons["vision.import"].waitForExistence(timeout: 20)); app.buttons["vision.import"].tap()
        XCTAssertTrue(app.buttons["Cancel"].firstMatch.waitForExistence(timeout: 20), app.debugDescription)
        if visibleFileItem("QRCatcher-Test-Imports") == nil {
            visibleFileItem("Browse")?.tap()
            if visibleFileItem("QRCatcher") == nil { selectFileItem("On My Apple Vision Pro") }
            selectFileItem("QRCatcher")
        }
        selectFileItem("QRCatcher-Test-Imports")
        selectFileItem(visibleFileItem("SyntheticQR.png") == nil ? "SyntheticQR" : "SyntheticQR.png")
        XCTAssertTrue(app.staticTexts["vision.payload"].waitForExistence(timeout: 20), app.debugDescription)
        XCTAssertEqual(app.staticTexts["vision.payload"].label, "QRCatcher 你好 🌈 123")
        app.terminate(); app.launch()
        let record = app.staticTexts["QRCatcher 你好 🌈 123"]
        XCTAssertTrue(record.waitForExistence(timeout: 15)); record.tap()
        XCTAssertEqual(app.staticTexts["vision.payload"].label, "QRCatcher 你好 🌈 123")
        capture("vision-files-import-reopened")
    }

    func testChineseEmptyPhotosResultAndOfflinePolicy() {
        XCTAssertTrue(app.buttons["vision.photos"].waitForExistence(timeout: 20))
        XCTAssertFalse(app.staticTexts["vision.payload"].exists)
        capture("vision-chinese-empty")
        app.buttons["vision.photos"].tap()
        let asset = app.images["PXGGridLayout-Info"].firstMatch
        XCTAssertTrue(asset.waitForExistence(timeout: 20), app.debugDescription); asset.tap()
        XCTAssertTrue(app.staticTexts["vision.payload"].waitForExistence(timeout: 20))
        XCTAssertEqual(app.staticTexts["vision.payload"].label, "QRCatcher 你好 🌈 123")
        XCTAssertEqual(app.buttons["vision.copy"].label, "复制")
        app.buttons["vision.copy"].tap()
        XCTAssertEqual(app.staticTexts["vision.status"].label, "已复制结果")
        capture("vision-chinese-result")
        app.buttons["vision.privacy"].tap()
        let body = app.staticTexts["privacy.offlineBody"]
        XCTAssertTrue(body.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(body.label.contains("本地数据可通过相应应用或系统删除，权限可在系统设置中撤回。"))
        XCTAssertTrue(body.label.contains("100mango@gmail.com"))
        capture("vision-chinese-policy")
        app.buttons["vision.privacyDone"].tap()
        XCTAssertTrue(app.buttons["vision.copy"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["vision.payload"].label, "QRCatcher 你好 🌈 123")
    }
}

// Test-runner-only stop. Returning false or throwing an XCTest assertion here
// would permit the default interruption handler to approve an unknown prompt.
@MainActor private func QRStopForUnexpectedInterruption(_ alert: XCUIElement) -> Never {
    fputs("QRCATCHER_UNEXPECTED_INTERRUPTION_ABORT_BEFORE_UI_ACTION\n", stderr); fflush(stderr)
    // Do not query AX or record a throwable assertion before this stop.
    abort()
}
