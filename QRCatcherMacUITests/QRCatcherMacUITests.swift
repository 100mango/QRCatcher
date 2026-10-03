import XCTest
import AppKit
import CryptoKit
import Security

@MainActor
final class QRCatcherMacUITests: XCTestCase {
    private var app: XCUIApplication!
    private var folder: URL!
    private var boundaryFolder: URL?
    private var root: URL { URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent() }

    override func setUpWithError() throws {
        continueAfterFailure = false
        folder = FileManager.default.temporaryDirectory.appendingPathComponent("QRCatcherUITest-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        app = XCUIApplication(url: expectedApplicationURL)
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        if isSandboxedProduct {
            // The actual sandbox app chooses its OS-provided Application Support
            // container. No absolute /tmp override or broad file grant is used.
            app.launchEnvironment["QRCATCHER_TEST_STORE_NAME"] = UUID().uuidString
            app.launchEnvironment["QRCATCHER_SANDBOX_PROOF"] = "1"
            let boundary = URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true).appendingPathComponent("QRCatcherBoundaryProbe-" + UUID().uuidString, isDirectory: true)
            try FileManager.default.createDirectory(at: boundary, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
            let bytes = Data("synthetic sandbox read sentinel".utf8)
            XCTAssertTrue(FileManager.default.createFile(atPath: boundary.appendingPathComponent("synthetic-read.txt").path, contents: bytes, attributes: [.posixPermissions: 0o600]))
            XCTAssertEqual(try Data(contentsOf: boundary.appendingPathComponent("synthetic-read.txt")), bytes)
            boundaryFolder = boundary
            app.launchEnvironment["QRCATCHER_SANDBOX_BOUNDARY"] = boundary.path
        } else { app.launchEnvironment["QRCATCHER_TEST_STORE"] = folder.appendingPathComponent("coredata.sqlite").path }
        dismissObservedRealityWidgetsCrash()
        app.launch(); verifyRunningApplication()
        XCTAssertTrue(app.buttons["mac.import"].waitForExistence(timeout: 20))
    }
    override func tearDownWithError() throws {
        if (testRun?.failureCount ?? 0) > 0 { print(app.debugDescription); try? screenshot("mac-failure") }
        app?.terminate(); if let folder { try? FileManager.default.removeItem(at: folder) }; if let boundaryFolder { try? FileManager.default.removeItem(at: boundaryFolder) }
    }

    private var expectedApplicationURL: URL {
        var runner = Bundle(for: Self.self).bundleURL
        while runner.pathExtension != "app", runner.pathComponents.count > 1 { runner.deleteLastPathComponent() }
        return runner.deletingLastPathComponent().appendingPathComponent("QRCatcherMac.app")
    }

    private var isSandboxedProduct: Bool {
        var code: SecStaticCode?
        guard SecStaticCodeCreateWithPath(expectedApplicationURL as CFURL, [], &code) == errSecSuccess, let code else { return false }
        var information: CFDictionary?
        guard SecCodeCopySigningInformation(code, SecCSFlags(rawValue: kSecCSSigningInformation), &information) == errSecSuccess,
              let dictionary = information as? [String: Any], let entitlements = dictionary[kSecCodeInfoEntitlementsDict as String] as? [String: Any] else { return false }
        return entitlements["com.apple.security.app-sandbox"] as? Bool == true
    }

    private func dismissObservedRealityWidgetsCrash() {
        // Exact non-permission crash notice observed after the Vision simulator
        // boot in run 37120587065. Never choose Report or handle other alerts.
        let notifications = XCUIApplication(bundleIdentifier: "com.apple.UserNotificationCenter")
        let dialog = notifications.dialogs.firstMatch
        let title = dialog.staticTexts.matching(NSPredicate(format: "value CONTAINS %@ OR label CONTAINS %@", "RealityWidgets quit unexpectedly", "RealityWidgets quit unexpectedly")).firstMatch
        guard title.exists else { return }
        print("OBSERVED_REALITY_WIDGETS_CRASH_NOTICE:", dialog.debugDescription)
        let ignore = dialog.buttons["Ignore"]
        guard ignore.exists else { XCTFail("Known crash notice has no accessible Ignore button; leaving it untouched"); return }
        ignore.click()
        let dismissed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: title)
        XCTAssertEqual(XCTWaiter.wait(for: [dismissed], timeout: 5), .completed)
    }

    private func verifyRunningApplication() {
        dismissObservedRealityWidgetsCrash()
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
        // Modern Xcode Debug executables can be stable launch stubs; hash the
        // actual debug dylib payload too, not just the launcher filename.
        var codeHashes: [String: String] = [:]
        if let files = try? FileManager.default.contentsOfDirectory(at: executable.deletingLastPathComponent(), includingPropertiesForKeys: nil) {
            for file in files where file.lastPathComponent == executable.lastPathComponent || file.pathExtension == "dylib" {
                if let data = try? Data(contentsOf: file) { codeHashes[file.lastPathComponent] = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
            }
        }
        XCTAssertNotNil(codeHashes["QRCatcherMac.debug.dylib"])
        let provenance: [String: Any] = ["code_payload_sha256": codeHashes, "pid": running.processIdentifier, "actual_bundle": actual.path, "actual_executable": executable.path,
                                        "expected_bundle": expected.path, "executable_sha256": hash, "product_app_sandbox": isSandboxedProduct]
        if let data = try? JSONSerialization.data(withJSONObject: provenance, options: .sortedKeys) {
            print("RUNNING_APP_PROVENANCE:", String(decoding: data, as: UTF8.self))
        }
    }

    private func fileDialog(path: String, button: String) {
        dismissObservedRealityWidgetsCrash()
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

    func testSandboxActualContainerLegacyHistoryAndUnselectedFileBoundary() throws {
        try XCTSkipUnless(isSandboxedProduct, "This gate executes in the separate minimal-entitlement sandbox lane")
        app.terminate()
        app.launchEnvironment.removeValue(forKey: "QRCATCHER_TEST_STORE_NAME")
        app.launchEnvironment["QRCATCHER_SANDBOX_FIXTURE"] = UUID().uuidString
        app.launch(); verifyRunningApplication()
        let row = app.staticTexts.matching(NSPredicate(format: "value CONTAINS %@ OR label CONTAINS %@", "Sandbox legacy duplicate", "Sandbox legacy duplicate")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 15)); row.click()
        let first = folder.appendingPathComponent("sandbox-before.json")
        app.buttons["mac.exportHistory"].click(); fileDialog(path: first.path, button: "Save")
        let saved = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: first)) as? [String: Any])
        let proof = try XCTUnwrap(saved["sandboxDiagnostics"] as? [String: Any])
        XCTAssertEqual(proof["sandboxed"] as? Bool, true)
        XCTAssertEqual(proof["unselectedReadRejected"] as? Bool, true, "The unrelated, never-selected synthetic home folder must remain unreadable: \(proof)")
        XCTAssertEqual(proof["unselectedWriteRejected"] as? Bool, true, "The process must be constrained by the actual sandbox: \(proof)")
        let home = try XCTUnwrap(proof["home"] as? String)
        XCTAssertEqual(proof["actualStoreURL"] as? String, home + "/Documents/coredata.sqlite")
        let rows = try XCTUnwrap(saved["records"] as? [[String: Any]])
        XCTAssertEqual(rows.count, 2)
        XCTAssertEqual(rows.compactMap { $0["payload"] as? String }, ["Sandbox legacy duplicate", "Sandbox legacy duplicate"])
        XCTAssertEqual(rows.compactMap { $0["createdAtUnixSeconds"] as? Double }, [1431993600,1431993500])
        app.terminate(); app.launch(); verifyRunningApplication()
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        importImage("unicode")
        XCTAssertTrue(app.staticTexts["mac.payload"].waitForExistence(timeout: 15))
        let after = folder.appendingPathComponent("sandbox-after.json")
        app.buttons["mac.exportHistory"].click(); fileDialog(path: after.path, button: "Save")
        let final = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: after)) as? [String: Any])
        XCTAssertEqual((final["records"] as? [[String: Any]])?.count, 3)
        print("ACTUAL_SANDBOX_E2E_PROOF:", proof)
        try screenshot("mac-sandbox-legacy-reopened")
    }

    func testSystemPhotosImportThenRealAppPicker() throws {
        try XCTSkipUnless(isSandboxedProduct, "Run populated system Photos selection once in the minimally entitled sandbox lane")
        let photos = XCUIApplication(bundleIdentifier: "com.apple.Photos")
        photos.launch()
        defer { photos.terminate() }
        // Only the normal first-use library start is accepted. Account, iCloud,
        // Intelligence and permission setup prompts are never blindly accepted.
        if photos.buttons["Get Started"].waitForExistence(timeout: 5) { photos.buttons["Get Started"].click() }
        print("PHOTOS_LIBRARY_INITIAL_UI:", photos.debugDescription)
        let file = photos.menuBarItems["File"]
        XCTAssertTrue(file.waitForExistence(timeout: 15), photos.debugDescription); file.click()
        let importMenu = photos.menuItems.matching(NSPredicate(format: "label BEGINSWITH %@", "Import")).firstMatch
        XCTAssertTrue(importMenu.isEnabled, photos.debugDescription); importMenu.click()
        photos.typeKey("g", modifierFlags: [.command, .shift])
        let path = photos.sheets.textFields.firstMatch
        XCTAssertTrue(path.waitForExistence(timeout: 5), photos.debugDescription)
        path.typeKey("a", modifierFlags: .command); path.typeText(root.appendingPathComponent("Tests/Fixtures/unicode.png").path)
        photos.typeKey(.return, modifierFlags: [])
        let open = photos.dialogs.buttons["OKButton"].firstMatch
        XCTAssertTrue(open.waitForExistence(timeout: 5), photos.debugDescription); open.click()
        let review = photos.buttons["Review for Import"]
        if review.waitForExistence(timeout: 3) { review.click() }
        let importAll = photos.buttons["Import All New Photos"]
        XCTAssertTrue(importAll.waitForExistence(timeout: 15), photos.debugDescription); importAll.click()
        let imported = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: importAll)
        XCTAssertEqual(XCTWaiter.wait(for: [imported], timeout: 20), .completed, photos.debugDescription)
        print("PHOTOS_LIBRARY_AFTER_IMPORT:", photos.debugDescription)
        app.activate(); verifyRunningApplication()
        app.buttons["mac.photos"].click()
        print("SYSTEM_PHOTOS_PICKER_UI:", app.debugDescription)
        let image = app.images["PXGGridLayout-Info"].firstMatch
        XCTAssertTrue(image.waitForExistence(timeout: 15), app.debugDescription); image.click()
        XCTAssertTrue(app.staticTexts["mac.payload"].waitForExistence(timeout: 20), app.debugDescription)
        let payload = app.staticTexts["mac.payload"]
        XCTAssertEqual((payload.value as? String) ?? payload.label, "QRCatcher 你好 🌈 123")
        try screenshot("mac-real-photos-import")
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
