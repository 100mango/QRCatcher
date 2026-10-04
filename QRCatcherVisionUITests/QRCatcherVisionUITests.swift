import XCTest
import Darwin
import UIKit

@MainActor
final class QRCatcherVisionUITests: XCTestCase {
    private var app: XCUIApplication!
    private var interruptionGuard: NSObjectProtocol?
    private var captureLease: String?
    private var captureSource: String?
    private var captureDevice: String?
    private var captureCase: String?
    private var captureScope: String?
    private var captureResult: String?
    private var captureStoreName = ""
    private func tracePhase(_ message: String) { print(message); fflush(stdout) }
    override func setUp() async throws {
        try await super.setUp()
        app = nil; captureLease = nil; captureSource = nil; captureDevice = nil
        captureCase = nil; captureScope = nil; captureResult = nil
        captureStoreName = ""
        continueAfterFailure = false
        // Installed before any app/system-app launch and retained through teardown.
        interruptionGuard = addUIInterruptionMonitor(withDescription: "Stop before every unexpected system interruption") { alert in
            QRStopForUnexpectedInterruption(alert)
        }
        // The current runner binds before any app launch/picker action. A
        // failed prerequisite throws and cannot enter an unbound workflow.
        try await bindCaptureRunner()
        app = XCUIApplication()
        let chinese = name.contains("testChineseEmptyPhotosResultAndOfflinePolicy")
        app.launchArguments = chinese ? ["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN"] : ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        captureStoreName = UUID().uuidString
        app.launchEnvironment["QRCATCHER_TEST_STORE_NAME"] = captureStoreName
        app.launch()
    }
    override func tearDown() async throws {
        tracePhase("VISION_TEARDOWN_ENTRY_BEFORE_FAILURE_COUNT")
        defer { if let interruptionGuard { removeUIInterruptionMonitor(interruptionGuard) } }
        let failures = testRun?.failureCount ?? 0
        tracePhase("VISION_TEARDOWN_AFTER_FAILURE_COUNT \(failures)")
        if let app {
            if failures > 0, captureLease != nil {
                tracePhase("VISION_TEARDOWN_BEFORE_FAILURE_CAPTURE")
                await capture("vision-failure")
                tracePhase("VISION_TEARDOWN_AFTER_FAILURE_CAPTURE")
            }
            tracePhase("VISION_TEARDOWN_BEFORE_APP_TERMINATE")
            app.terminate()
            tracePhase("VISION_TEARDOWN_AFTER_APP_TERMINATE")
        }
        if let captureLease {
            let request = FileManager.default.temporaryDirectory.appendingPathComponent("QRCatcher-runner-" + captureLease + ".json")
            try? FileManager.default.removeItem(at: request)
            try? FileManager.default.removeItem(at: request.deletingPathExtension().appendingPathExtension("ack"))
        }
        captureLease = nil; captureSource = nil; captureDevice = nil
        captureCase = nil; captureScope = nil; captureResult = nil
        captureStoreName = ""
        tracePhase("VISION_TEARDOWN_FINISHED")
    }
    private func bindCaptureRunner() async throws {
        let id = UUID().uuidString
        let runner = try XCTUnwrap(Bundle.main.bundleIdentifier)
        let pid = Int(ProcessInfo.processInfo.processIdentifier)
        let methods = ["testRealPhotosImportCopyAndReopen", "testRealFilesImportAndReopen", "testChineseEmptyPhotosResultAndOfflinePolicy"]
        // Bind the actual XCTest identity, rather than inferring a case from
        // an arbitrary substring or silently selecting a default workflow.
        let actualMethod = try XCTUnwrap(methods.first { method in
            name == "-[QRCatcherVisionUITests.QRCatcherVisionUITests \(method)]"
                || name == "-[QRCatcherVisionUITests \(method)]"
        }, "Unrecognized actual Vision XCTest method identity")
        let exports = actualMethod == "testRealPhotosImportCopyAndReopen"
        let request = FileManager.default.temporaryDirectory.appendingPathComponent("QRCatcher-runner-" + id + ".json")
        let ack = request.deletingPathExtension().appendingPathExtension("ack")
        var accepted = false
        defer {
            try? FileManager.default.removeItem(at: ack)
            if !accepted { try? FileManager.default.removeItem(at: request) }
        }
        let descriptor = try JSONSerialization.data(withJSONObject: ["id": id, "runner": runner, "pid": pid, "exports": exports, "case": actualMethod])
        try descriptor.write(to: request, options: .atomic)
        print("QRCATCHER_VISION_RUNNER_READY:" + id); fflush(stdout)
        // One 20-second public lookup, or two for the export case's own app
        // container. This setup has its own bounded ACK and no retry route.
        let seconds = exports ? 60 : 30
        let bindingStarted = ProcessInfo.processInfo.systemUptime
        let deadline = ContinuousClock.now.advanced(by: .seconds(seconds))
        while ContinuousClock.now < deadline && !FileManager.default.fileExists(atPath: ack.path) {
            try await Task.sleep(nanoseconds: 200_000_000)
        }
        tracePhase("VISION_BINDING_ACK_WAIT_FINISHED exists=\(FileManager.default.fileExists(atPath: ack.path)) elapsed=\(ProcessInfo.processInfo.systemUptime - bindingStarted) configured_seconds=\(seconds)")
        let result = try JSONSerialization.jsonObject(with: Data(contentsOf: ack)) as? [String: Any]
        let scopes = [
            "visionos_photos": ["testRealPhotosImportCopyAndReopen", "VisionPhotosUIResults.xcresult"],
            "visionos_files": ["testRealFilesImportAndReopen", "VisionFilesUIResults.xcresult"],
            "visionos_chinese": ["testChineseEmptyPhotosResultAndOfflinePolicy", "VisionChineseUIResults.xcresult"],
            "visionos_largest": ["testChineseEmptyPhotosResultAndOfflinePolicy", "VisionLargestUIResults.xcresult"]
        ]
        guard result?["success"] as? Bool == true, result?["lease"] as? String == id,
              result?["runner"] as? String == runner, result?["pid"] as? Int == pid,
              result?["exports"] as? Bool == exports,
              result?["case"] as? String == actualMethod,
              let scope = result?["scope"] as? String,
              let resultName = result?["result"] as? String,
              scopes[scope] == [actualMethod, resultName],
              let source = result?["source_commit"] as? String,
              source.range(of: "^[0-9a-f]{40}$", options: .regularExpression) != nil,
              let device = result?["device"] as? String, UUID(uuidString: device)?.uuidString == device else {
            throw NSError(domain: "QRCatcherVisionRunnerBinding", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "No matching source/device/current-runner binding before UI"])
        }
        captureLease = id; captureSource = source; captureDevice = device; accepted = true
        captureCase = actualMethod; captureScope = scope; captureResult = resultName
    }
    private func capture(_ name: String) async {
        if name == "vision-failure" { tracePhase("VISION_FAILURE_CAPTURE_ENTRY") }
        guard let captureLease, let captureSource, let captureDevice,
              let captureCase, let captureScope, let captureResult else {
            if name == "vision-failure" { print("VISION_FAILURE_CAPTURE_WITHOUT_BINDING") }
            else { XCTFail("No current runner binding; no success checkpoint requested") }
            return
        }
        if name != "vision-failure" {
            do { try app.performAccessibilityAudit(for: .all) { issue in print("VISION_ACCESSIBILITY_ISSUE", issue.compactDescription, issue.detailedDescription, issue.element?.debugDescription ?? "no issue element"); return false } }
            catch { XCTFail("VISION accessibility audit failed: \(error)") }
        }
        // Audits can scroll the sheet. Re-establish the actual visible policy
        // ending before the held pixel capture, rather than trusting its AX label.
        if name == "vision-chinese-policy" { revealPolicyEnding() }
        // Native Vision XCTest explicitly reports manual screenshots unsupported.
        // The cloud script takes actual public simctl pixels at this checkpoint.
        if name != "vision-failure" {
            let description = String(app.debugDescription.prefix(20000))
            let attachment = XCTAttachment(string: description); attachment.name = name + "-accessibility"; attachment.lifetime = .keepAlways; add(attachment)
        } else {
            // A failed AX query can leave its snapshot service unresponsive.
            // Preserve XCTest's original issue; do not repeat that query while
            // teardown only requests a bounded, non-AX simulator screenshot.
            tracePhase("VISION_FAILURE_CAPTURE_WITHOUT_NEW_AX_QUERY")
        }
        let id = UUID().uuidString
        let request = FileManager.default.temporaryDirectory.appendingPathComponent("QRCatcher-capture-" + id + ".json")
        let ack = request.deletingPathExtension().appendingPathExtension("ack")
        do {
            if name == "vision-failure" { tracePhase("VISION_FAILURE_CAPTURE_BEFORE_REQUEST_WRITE " + id) }
            let descriptor = try JSONSerialization.data(withJSONObject: ["id": id, "name": name, "test_store": captureStoreName,
                "runner": Bundle.main.bundleIdentifier ?? "", "lease": captureLease,
                "pid": Int(ProcessInfo.processInfo.processIdentifier), "source_commit": captureSource, "device": captureDevice,
                "case": captureCase, "scope": captureScope, "result": captureResult])
            try descriptor.write(to: request, options: .atomic)
            print("QRCATCHER_VISION_CAPTURE_REQUEST:" + id); fflush(stdout)
            let deadline = ContinuousClock.now.advanced(by: .seconds(100))
            // Hold the same UI state while yielding the runner's main actor to
            // its system services. Never block that actor for the ACK deadline.
            while ContinuousClock.now < deadline && !FileManager.default.fileExists(atPath: ack.path) {
                try await Task.sleep(nanoseconds: 200_000_000)
            }
            let result = try JSONSerialization.jsonObject(with: Data(contentsOf: ack)) as? [String: Any]
            if name == "vision-failure" {
                print("VISION_FAILURE_CAPTURE_DIAGNOSTIC", String(describing: result))
            } else {
                XCTAssertEqual(result?["id"] as? String, id)
                XCTAssertEqual(result?["lease"] as? String, captureLease)
                XCTAssertEqual(result?["source_commit"] as? String, captureSource)
                XCTAssertEqual(result?["device"] as? String, captureDevice)
                XCTAssertEqual(result?["case"] as? String, captureCase)
                XCTAssertEqual(result?["scope"] as? String, captureScope)
                XCTAssertEqual(result?["result"] as? String, captureResult)
                XCTAssertEqual(result?["success"] as? Bool, true, "Held simulator checkpoint failed: \(String(describing: result))")
            }
        } catch {
            if name == "vision-failure" { print("VISION_FAILURE_CAPTURE_DIAGNOSTIC", error) }
            else { XCTFail("Held simulator capture acknowledgement: \(error)") }
        }
        try? FileManager.default.removeItem(at: request); try? FileManager.default.removeItem(at: ack)
    }
    private func revealPolicyEnding() {
        let scroll = app.scrollViews["vision.privacyScroll"]
        let end = app.staticTexts["privacy.offlineEnd"]
        XCTAssertTrue(scroll.waitForExistence(timeout: 5)); XCTAssertTrue(end.exists)
        for _ in 0..<12 {
            let lastLine = CGRect(x: end.frame.minX, y: end.frame.maxY - min(end.frame.height, UIFont.preferredFont(forTextStyle: .body).lineHeight),
                                  width: end.frame.width, height: min(end.frame.height, UIFont.preferredFont(forTextStyle: .body).lineHeight))
            if end.isHittable && scroll.frame.contains(lastLine) { return }
            scroll.swipeUp()
        }
        XCTFail("The rendered end of the policy is not reachable inside its scroll viewport: \(end.debugDescription)")
    }
    private func saveUsingSystemFileExporter(_ button: String, name: String, checkpoint: String) async {
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
        let outcome = await XCTWaiter.fulfillment(of: [finished], timeout: 20)
        XCTAssertEqual(outcome, .completed, app.debugDescription)
        await capture(checkpoint) // Host independently verifies bytes read from the saved URL.
    }
    private func readyNativePhotoAsset() async -> XCUIElement? {
        // These stable identifiers were observed in the actual SDK 27 picker.
        // Do not depend on its localized Photos navigation title or match an
        // unrelated image elsewhere in the app. Polling performs no UI action.
        let grids = app.scrollViews.matching(identifier: "photosView_content_scroll_view")
        let grid = grids.firstMatch
        let asset = grid.images["PXGGridLayout-Info"].firstMatch
        let ready = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == true AND hittable == true"), object: asset)
        let readinessStarted = ProcessInfo.processInfo.systemUptime
        tracePhase("VISION_PHOTOS_READINESS_BEGIN configured_seconds=20")
        let outcome = await XCTWaiter.fulfillment(of: [ready], timeout: 20)
        tracePhase("VISION_PHOTOS_READINESS_END outcome=\(outcome.rawValue) elapsed=\(ProcessInfo.processInfo.systemUptime - readinessStarted) configured_seconds=20")
        guard outcome == .completed else {
            XCTFail("Native Photos asset was not present and hittable in its observed viewport within 20 seconds")
            return nil
        }
        guard grids.count == 1, grid.exists, asset.exists, asset.isHittable else {
            XCTFail("Native Photos viewport became ambiguous or its asset lost readiness before selection")
            return nil
        }
        return asset
    }
    func testRealPhotosImportCopyAndReopen() async {
        XCTAssertTrue(app.buttons["vision.photos"].waitForExistence(timeout: 20))
        app.buttons["vision.photos"].tap()
        guard let asset = await readyNativePhotoAsset() else { return }
        asset.tap()
        XCTAssertTrue(app.staticTexts["vision.payload"].waitForExistence(timeout: 20), app.debugDescription)
        XCTAssertEqual(app.staticTexts["vision.payload"].label, "QRCatcher 你好 🌈 123")
        XCTAssertFalse(app.buttons["vision.openWebsite"].exists)
        app.buttons["vision.copy"].tap()
        XCTAssertEqual(app.staticTexts["vision.status"].label, "Result copied")
        await capture("vision-imported-qr")
        app.terminate(); app.launch()
        let record = app.staticTexts["QRCatcher 你好 🌈 123"]
        XCTAssertTrue(record.waitForExistence(timeout: 15)); record.tap()
        XCTAssertTrue(app.buttons["vision.exportQR"].waitForExistence(timeout: 5))
        await capture("vision-reopened-history")
        await saveUsingSystemFileExporter("vision.exportQR", name: "QRCatcher Synthetic QR", checkpoint: "vision-exported-qr")
        // Copy resets the status, so a prior successful save cannot satisfy the
        // second completion assertion before that system exporter actually ends.
        app.buttons["vision.copy"].tap()
        await saveUsingSystemFileExporter("vision.exportHistory", name: "QRCatcher Synthetic History", checkpoint: "vision-exported-history")
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
    func testRealFilesImportAndReopen() async {
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
        await capture("vision-files-import-reopened")
    }

    func testChineseEmptyPhotosResultAndOfflinePolicy() async {
        XCTAssertTrue(app.buttons["vision.photos"].waitForExistence(timeout: 20))
        XCTAssertFalse(app.staticTexts["vision.payload"].exists)
        await capture("vision-chinese-empty")
        app.buttons["vision.photos"].tap()
        guard let asset = await readyNativePhotoAsset() else { return }
        asset.tap()
        XCTAssertTrue(app.staticTexts["vision.payload"].waitForExistence(timeout: 20))
        XCTAssertEqual(app.staticTexts["vision.payload"].label, "QRCatcher 你好 🌈 123")
        XCTAssertEqual(app.buttons["vision.copy"].label, "复制")
        app.buttons["vision.copy"].tap()
        XCTAssertEqual(app.staticTexts["vision.status"].label, "已复制结果")
        await capture("vision-chinese-result")
        app.buttons["vision.privacy"].tap()
        let body = app.staticTexts["privacy.offlineBody"]
        XCTAssertTrue(body.waitForExistence(timeout: 10), app.debugDescription)
        let ending = app.staticTexts["privacy.offlineEnd"]
        XCTAssertEqual(ending.label, "本地数据可通过相应应用或系统删除，权限可在系统设置中撤回。")
        XCTAssertTrue(body.label.contains("100mango@gmail.com"))
        await capture("vision-chinese-policy")
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
