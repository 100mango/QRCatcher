import XCTest
import AppKit
import CryptoKit

@MainActor
final class QRCatcherMacUITests: XCTestCase {
    private var app: XCUIApplication!
    private var folder: URL!
    private var root: URL { URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent() }

    override func setUpWithError() throws {
        continueAfterFailure = false
        folder = FileManager.default.temporaryDirectory.appendingPathComponent("QRCatcherUITest-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        app = XCUIApplication(url: expectedApplicationURL)
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launchEnvironment["QRCATCHER_TEST_STORE"] = folder.appendingPathComponent("coredata.sqlite").path
        app.launch(); verifyRunningApplication()
        XCTAssertTrue(app.buttons["mac.import"].waitForExistence(timeout: 20))
    }
    override func tearDownWithError() throws {
        if (testRun?.failureCount ?? 0) > 0 { print(app.debugDescription); try? screenshot("mac-failure") }
        app?.terminate(); if let folder { try? FileManager.default.removeItem(at: folder) }
    }

    private var expectedApplicationURL: URL {
        var runner = Bundle(for: Self.self).bundleURL
        while runner.pathExtension != "app", runner.pathComponents.count > 1 { runner.deleteLastPathComponent() }
        return runner.deletingLastPathComponent().appendingPathComponent("QRCatcherMac.app")
    }

    private func verifyRunningApplication() {
        XCTAssertTrue(app.buttons["mac.import"].waitForExistence(timeout: 20))
        let candidates = NSRunningApplication.runningApplications(withBundleIdentifier: "100mango.QRCatcher").filter { !$0.isTerminated }
        XCTAssertEqual(candidates.count, 1, "Exactly one target process must be running")
        guard let running = candidates.first, let actual = running.bundleURL, let executable = running.executableURL else { XCTFail("Target process has no bundle/executable identity"); return }
        let expected = expectedApplicationURL
        XCTAssertEqual(actual.resolvingSymlinksInPath().standardizedFileURL, expected.resolvingSymlinksInPath().standardizedFileURL,
                       "XCTest must launch the intended adjacent Debug product, never the same-bundle Release product")
        XCTAssertTrue(app.debugDescription.contains("pid: \(running.processIdentifier)"))
        let bytes = (try? Data(contentsOf: executable)) ?? Data()
        XCTAssertFalse(bytes.isEmpty)
        let hash = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        let provenance: [String: Any] = ["pid": running.processIdentifier, "actual_bundle": actual.path, "actual_executable": executable.path,
                                        "expected_bundle": expected.path, "executable_sha256": hash]
        if let data = try? JSONSerialization.data(withJSONObject: provenance, options: .sortedKeys) {
            print("RUNNING_APP_PROVENANCE:", String(decoding: data, as: UTF8.self))
        }
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
        if button == "Save" {
            let finished = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in FileManager.default.fileExists(atPath: url.path) }, object: nil)
            let outcome = XCTWaiter.wait(for: [finished], timeout: 8)
            if outcome != .completed {
                print("EXPORT_FOLDER_CONTENTS:", (try? FileManager.default.contentsOfDirectory(atPath: url.deletingLastPathComponent().path)) ?? [])
                print("EXPORT_UI:", app.debugDescription)
                try? screenshot("mac-failure")
            }
            XCTAssertEqual(outcome, .completed, "The native Save action must produce the requested file before readback")
        }
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
        app.terminate(); app.launch(); verifyRunningApplication()
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
        app.launch(); verifyRunningApplication()
        XCTAssertTrue(app.buttons["mac.import"].waitForExistence(timeout: 20))
        importImage("unicode")
        XCTAssertTrue(app.staticTexts["mac.payload"].waitForExistence(timeout: 15))
        XCTAssertEqual(app.buttons["mac.copy"].label, "复制")
        app.buttons["mac.copy"].click()
        XCTAssertEqual(NSPasteboard.general.string(forType: .string), "QRCatcher 你好 🌈 123")
        let png = folder.appendingPathComponent("chinese-result.png")
        app.buttons["mac.exportQR"].click(); fileDialog(path: png.path, button: "Save")
        XCTAssertTrue(FileManager.default.fileExists(atPath: png.path))
        app.terminate(); app.launch(); verifyRunningApplication()
        let row = app.staticTexts.matching(NSPredicate(format: "value CONTAINS %@ OR label CONTAINS %@", "QRCatcher 你好", "QRCatcher 你好")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 10)); row.click()
        XCTAssertTrue(app.buttons["mac.copy"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.buttons["mac.copy"].label, "复制")
        try screenshot("mac-chinese-reopened")
        app.buttons["mac.privacy"].click()
        let body = app.staticTexts["privacy.offlineBody"]
        XCTAssertTrue(body.waitForExistence(timeout: 5))
        let text = (body.value as? String) ?? body.label
        XCTAssertTrue(text.contains("本地数据可通过相应应用或系统删除，权限可在系统设置中撤回。"))
        XCTAssertTrue(text.contains("系统 iCloud 同步"))
        try screenshot("mac-chinese-policy")
        app.buttons["完成"].firstMatch.click()
    }

    func testNativeWindowResizeKeepsFullActionTitles() throws {
        let image = try XCTUnwrap(NSImage(contentsOf: root.appendingPathComponent("Tests/Fixtures/ascii.png")))
        NSPasteboard.general.clearContents(); XCTAssertTrue(NSPasteboard.general.writeObjects([image]))
        app.buttons["mac.paste"].click()
        XCTAssertTrue(app.staticTexts["mac.payload"].waitForExistence(timeout: 15))
        let window = app.windows["main"]
        let before = window.frame
        let right = window.coordinate(withNormalizedOffset: CGVector(dx: 1, dy: 0.5)).withOffset(CGVector(dx: -1, dy: 0))
        right.click(forDuration: 0.3, thenDragTo: right.withOffset(CGVector(dx: -264, dy: 0)))
        let bottom = window.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 1)).withOffset(CGVector(dx: 0, dy: -1))
        bottom.click(forDuration: 0.3, thenDragTo: bottom.withOffset(CGVector(dx: 0, dy: -154)))
        XCTAssertLessThan(window.frame.width, before.width - 100)
        XCTAssertLessThan(window.frame.height, before.height - 60)
        let scroll = app.scrollViews.containing(.button, identifier: "mac.exportQR").firstMatch
        if !app.buttons["mac.copy"].isHittable { scroll.scroll(byDeltaX: 0, deltaY: -500) }
        for (identifier, title) in [("mac.copy", "Copy"), ("mac.exportQR", "Export QR Image…"), ("mac.openWebsite", "Open in Browser")] {
            let button = app.buttons[identifier]
            XCTAssertTrue(button.isHittable, button.debugDescription)
            XCTAssertEqual(button.label, title)
            XCTAssertTrue(window.frame.contains(button.frame), button.debugDescription)
            // The control uses the system regular button font. This catches a
            // constrained one-line title even when its AX label stays complete.
            let fullText = (title as NSString).size(withAttributes: [.font: NSFont.systemFont(ofSize: NSFont.systemFontSize)])
            XCTAssertGreaterThanOrEqual(button.frame.width, ceil(fullText.width))
            XCTAssertGreaterThanOrEqual(button.frame.height, ceil(fullText.height))
        }
        app.buttons["mac.copy"].click()
        XCTAssertEqual(NSPasteboard.general.string(forType: .string), "https://example.com/qrcatcher?source=golden")
        try screenshot("mac-minimum-window")
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
        let policy = app.staticTexts["privacy.offlineBody"]
        XCTAssertTrue(policy.waitForExistence(timeout: 5))
        let text = (policy.value as? String) ?? policy.label
        XCTAssertTrue(text.contains("100mango@gmail.com"))
        XCTAssertTrue(text.contains("Local data can be deleted through the relevant app or system, and permissions can be revoked in system settings."))
        try screenshot("mac-english-policy")
        app.buttons["Done"].firstMatch.click()
        XCTAssertTrue(app.buttons["mac.import"].exists)
    }
}
