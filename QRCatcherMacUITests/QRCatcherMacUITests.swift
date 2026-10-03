import XCTest
import AppKit

@MainActor
final class QRCatcherMacUITests: XCTestCase {
    private var app: XCUIApplication!
    private var folder: URL!
    private var root: URL { URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent() }

    override func setUpWithError() throws {
        continueAfterFailure = false
        folder = FileManager.default.temporaryDirectory.appendingPathComponent("QRCatcherUITest-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        app = XCUIApplication()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launchEnvironment["QRCATCHER_TEST_STORE"] = folder.appendingPathComponent("coredata.sqlite").path
        app.launch()
        XCTAssertTrue(app.buttons["mac.import"].waitForExistence(timeout: 20))
    }
    override func tearDownWithError() throws {
        if (testRun?.failureCount ?? 0) > 0 { print(app.debugDescription); try? screenshot("mac-failure") }
        app?.terminate(); if let folder { try? FileManager.default.removeItem(at: folder) }
    }

    private func fileDialog(path: String, button: String) {
        let url = URL(fileURLWithPath: path)
        if button == "Save" {
            let name = app.dialogs.textFields["saveAsNameTextField"]
            XCTAssertTrue(name.waitForExistence(timeout: 5))
            name.click(); name.typeKey("a", modifierFlags: .command); name.typeText(url.lastPathComponent)
        }
        app.typeKey("g", modifierFlags: [.command, .shift])
        let field = app.sheets.textFields.firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 5), app.debugDescription)
        field.typeKey("a", modifierFlags: .command)
        field.typeText(button == "Save" ? url.deletingLastPathComponent().path : path)
        app.typeKey(.return, modifierFlags: [])
        // The visible AppKit panel and Touch Bar expose duplicate titles.
        // Use the actual panel control identifier observed in the AX hierarchy.
        let confirm = app.dialogs.buttons["OKButton"].firstMatch
        XCTAssertTrue(confirm.waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertTrue(confirm.isEnabled, app.debugDescription)
        confirm.click()
    }
    private func importImage(_ name: String) {
        app.buttons["mac.import"].click()
        fileDialog(path: root.appendingPathComponent("Tests/Fixtures/\(name).png").path, button: "Read QR Code")
    }
    private func screenshot(_ name: String) throws {
        let png = XCUIScreen.main.screenshot().pngRepresentation
        let bitmap = try XCTUnwrap(NSBitmapImageRep(data: png))
        let jpeg = try XCTUnwrap(bitmap.representation(using: .jpeg, properties: [NSBitmapImageRep.PropertyKey.compressionFactor: 0.55]))
        XCTAssertLessThanOrEqual(jpeg.count, 800 * 1024)
        let attachment = XCTAttachment(data: jpeg, uniformTypeIdentifier: "public.jpeg")
        attachment.name = name; attachment.lifetime = XCTAttachment.Lifetime.keepAlways; add(attachment)
    }

    func testImportCopyExportReopenAndSearch() throws {
        importImage("unicode")
        let payload = app.staticTexts["mac.payload"]
        XCTAssertTrue(payload.waitForExistence(timeout: 15))
        XCTAssertEqual(payload.value as? String ?? payload.label, "QRCatcher 你好 🌈 123")
        XCTAssertFalse(app.buttons["mac.openWebsite"].exists)
        app.buttons["mac.copy"].click()
        XCTAssertEqual(NSPasteboard.general.string(forType: .string), "QRCatcher 你好 🌈 123")
        try screenshot("mac-imported-unicode")
        let png = folder.appendingPathComponent("roundtrip.png")
        app.buttons["mac.exportQR"].click()
        fileDialog(path: png.path, button: "Save")
        XCTAssertTrue(FileManager.default.fileExists(atPath: png.path))
        let json = folder.appendingPathComponent("history.json")
        app.buttons["mac.exportHistory"].click()
        fileDialog(path: json.path, button: "Save")
        let export = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: json)) as? [String: Any])
        XCTAssertEqual((export["records"] as? [[String:Any]])?.first?["payload"] as? String, "QRCatcher 你好 🌈 123")
        app.terminate(); app.launch()
        XCTAssertTrue(app.buttons["mac.import"].waitForExistence(timeout: 20))
        let row = app.staticTexts.containing(NSPredicate(format: "value CONTAINS %@ OR label CONTAINS %@", "QRCatcher 你好", "QRCatcher 你好")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 10)); row.click()
        XCTAssertTrue(app.staticTexts["mac.payload"].waitForExistence(timeout: 5))
        app.buttons["mac.import"].click(); fileDialog(path: png.path, button: "Read QR Code")
        XCTAssertTrue(app.staticTexts["mac.status"].waitForExistence(timeout: 5))
        let search = app.searchFields.firstMatch
        XCTAssertTrue(search.exists); search.click(); search.typeText("does-not-exist")
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "value == %@ OR label == %@", "No matching results", "No matching results")).firstMatch.waitForExistence(timeout: 5))
        search.typeKey("a", modifierFlags: .command); search.typeKey(.delete, modifierFlags: [])
        try screenshot("mac-reopened-history")
    }

    func testPasteActualQRImageAndCancelExport() throws {
        let image = try XCTUnwrap(NSImage(contentsOf: root.appendingPathComponent("Tests/Fixtures/ascii.png")))
        NSPasteboard.general.clearContents()
        XCTAssertTrue(NSPasteboard.general.writeObjects([image]))
        app.buttons["mac.paste"].click()
        XCTAssertTrue(app.staticTexts["mac.payload"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.buttons["mac.openWebsite"].exists)
        XCTAssertEqual(app.state, .runningForeground)
        app.buttons["mac.exportQR"].click()
        app.dialogs.buttons["CancelButton"].firstMatch.click()
        XCTAssertTrue(app.buttons["mac.copy"].exists)
        app.buttons["mac.copy"].click()
        XCTAssertEqual(NSPasteboard.general.string(forType: .string), "https://example.com/qrcatcher?source=golden")
        try screenshot("mac-pasted-url")
    }

    func testChineseCriticalFlow() throws {
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN"]
        app.launch()
        XCTAssertTrue(app.buttons["mac.import"].waitForExistence(timeout: 20))
        importImage("unicode")
        XCTAssertTrue(app.staticTexts["mac.payload"].waitForExistence(timeout: 15))
        XCTAssertEqual(app.buttons["mac.copy"].label, "复制")
        app.buttons["mac.copy"].click()
        XCTAssertEqual(NSPasteboard.general.string(forType: .string), "QRCatcher 你好 🌈 123")
        let png = folder.appendingPathComponent("chinese-result.png")
        app.buttons["mac.exportQR"].click(); fileDialog(path: png.path, button: "Save")
        XCTAssertTrue(FileManager.default.fileExists(atPath: png.path))
        app.terminate(); app.launch()
        let row = app.staticTexts.matching(NSPredicate(format: "value CONTAINS %@ OR label CONTAINS %@", "QRCatcher 你好", "QRCatcher 你好")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 10)); row.click()
        XCTAssertTrue(app.buttons["mac.copy"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.buttons["mac.copy"].label, "复制")
        try screenshot("mac-chinese-reopened")
    }

    func testInvalidImageCancelAndCameraAbsence() throws {
        app.buttons["mac.import"].click()
        app.dialogs.buttons["CancelButton"].firstMatch.click()
        XCTAssertFalse(app.staticTexts["mac.payload"].exists)
        importImage("invalid")
        let noCode = NSPredicate(format: "value CONTAINS %@ OR label CONTAINS %@", "No QR code", "No QR code")
        XCTAssertTrue(app.staticTexts.matching(noCode).firstMatch.waitForExistence(timeout: 10))
        app.buttons["mac.camera"].click()
        app.buttons["mac.cameraStart"].click()
        let status = app.staticTexts["mac.cameraStatus"]
        XCTAssertTrue(status.waitForExistence(timeout: 5))
        XCTAssertTrue(status.label.contains("No camera") || (status.value as? String)?.contains("No camera") == true, "Hosted cloud test must report the actual camera state: \(status.debugDescription)")
        try screenshot("mac-camera-unavailable")
        app.buttons["Done"].firstMatch.click()
        app.buttons["mac.privacy"].click()
        XCTAssertTrue(app.staticTexts["Questions: 100mango@gmail.com"].waitForExistence(timeout: 5))
        app.buttons["Done"].firstMatch.click()
        XCTAssertTrue(app.buttons["mac.import"].exists)
    }
}
