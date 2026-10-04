import XCTest
import Darwin
import UIKit

@MainActor
final class QRCatcherTVUITests: XCTestCase {
    private var app: XCUIApplication!
    private var interruptionGuard: NSObjectProtocol?
    override func setUpWithError() throws {
        continueAfterFailure = false
        // Installed before any app/system-app launch and retained through teardown.
        interruptionGuard = addUIInterruptionMonitor(withDescription: "Stop before every unexpected system interruption") { alert in
            QRStopForUnexpectedInterruption(alert)
        }
        app = XCUIApplication()
        app.launchArguments = ["-AppleLanguages","(en)","-AppleLocale","en_US"]
        app.launchEnvironment["QRCATCHER_TV_TEST_STORE"] = UUID().uuidString
        app.launch()
    }
    override func tearDownWithError() throws {
        defer { if let interruptionGuard { removeUIInterruptionMonitor(interruptionGuard) } }

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
            // Exact title and usage text retained from run 37144655090. Nested
            // tvOS button duplicates are expected; the action stays in this alert.
            let alert = system.alerts["Allow “QRCatcher” to access your photo library?"].firstMatch
            guard alert.exists,
                  alert.staticTexts["Choose QR images and verify QR images you save in Photos. Processing happens on this TV."].exists,
                  alert.buttons["Don’t Allow"].firstMatch.exists,
                  alert.buttons["Allow All Photos"].firstMatch.isEnabled else {
                QRStopForUnexpectedInterruption(system.alerts.firstMatch)
            }
            print("TV_OBSERVED_SYSTEM_PHOTOS_DIALOG:", alert.debugDescription)
            focusAndSelect(alert.buttons["Allow All Photos"].firstMatch, root: alert)
        } else {
            print("TV_PHOTOS_PERMISSION_SYSTEM_UI:", system.debugDescription)
        }
    }
    private func capture(_ name: String, focused target: XCUIElement? = nil) {
        // Capture the asserted remote-focus state before the system audit visits
        // accessibility elements and potentially changes focus to the first row.
        let pixels = XCUIScreen.main.screenshot().image
        guard let data = pixels.jpegData(compressionQuality: 0.45) else { XCTFail("TV screenshot unavailable"); return }
        XCTAssertLessThanOrEqual(data.count, 800 * 1024)
        let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.jpeg")
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
        if let target {
            let cell = app.descendants(matching: .cell).matching(NSPredicate(format: "hasFocus == true")).firstMatch
            let ownedCell = cell.exists && cell.buttons.count == 1 && cell.buttons[target.identifier].exists
            XCTAssertTrue(target.hasFocus || ownedCell, "Named focus screenshot must retain the requested real focus owner")
            print("TV_FOCUS_AT_PIXEL_CHECKPOINT", name, target.debugDescription, cell.exists ? cell.debugDescription : "no focused cell")
            if target.identifier == "tv.deleteRecord" { assertFocusedDeleteContrast(pixels, labelFrame: target.frame) }
        }
        if name != "tv-failure" {
            do { try app.performAccessibilityAudit(for: .all) { issue in print("TV_ACCESSIBILITY_ISSUE", issue.compactDescription, issue.detailedDescription, issue.element?.debugDescription ?? "no issue element"); return false } }
            catch { XCTFail("TV accessibility audit failed: \(error)") }
        }
    }
    private func assertFocusedDeleteContrast(_ screenshot: UIImage, labelFrame: CGRect) {
        guard let full = screenshot.cgImage else { XCTFail("No native screenshot pixels"); return }
        let scaleX = CGFloat(full.width) / screenshot.size.width
        let scaleY = CGFloat(full.height) / screenshot.size.height
        let cropRect = CGRect(x: labelFrame.minX * scaleX, y: labelFrame.minY * scaleY,
                              width: labelFrame.width * scaleX, height: labelFrame.height * scaleY).integral
        guard cropRect.minX >= 0, cropRect.minY >= 0, cropRect.maxX <= CGFloat(full.width), cropRect.maxY <= CGFloat(full.height),
              // Largest public-trait text legitimately occupies more pixels than
              // the ordinary 369×72 crop. Keep an explicit one-megapixel bound
              // while measuring original glyph pixels without resampling.
              let crop = full.cropping(to: cropRect), crop.width * crop.height <= 1_000_000 else {
            XCTFail("Focused Delete label does not have a bounded screen crop"); return
        }
        var rgba = [UInt8](repeating: 0, count: crop.width * crop.height * 4)
        let drew = rgba.withUnsafeMutableBytes { buffer -> Bool in
            guard let color = CGColorSpace(name: CGColorSpace.sRGB),
                  let context = CGContext(data: buffer.baseAddress, width: crop.width, height: crop.height,
                                          bitsPerComponent: 8, bytesPerRow: crop.width * 4, space: color,
                                          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue) else { return false }
            context.draw(crop, in: CGRect(x: 0, y: 0, width: CGFloat(crop.width), height: CGFloat(crop.height))); return true
        }
        XCTAssertTrue(drew)
        func linear(_ value: UInt8) -> Double {
            let s = Double(value) / 255
            return s <= 0.04045 ? s / 12.92 : pow((s + 0.055) / 1.055, 2.4)
        }
        let values = stride(from: 0, to: rgba.count, by: 4).map {
            0.2126 * linear(rgba[$0]) + 0.7152 * linear(rgba[$0 + 1]) + 0.0722 * linear(rgba[$0 + 2])
        }.sorted()
        let foreground = values[values.count / 20], background = values[values.count * 9 / 10]
        let contrast = (background + 0.05) / (foreground + 0.05)
        print("TV_FOCUSED_DELETE_PIXEL_CONTRAST", cropRect, foreground, background, contrast)
        // This specific runtime state has a white focused card. The whole exact
        // label crop must contain dark glyph pixels, not the observed pink-on-white.
        XCTAssertGreaterThan(background, 0.85)
        XCTAssertGreaterThanOrEqual(contrast, 4.5, "Actual focused Delete glyph/background contrast")
    }
    func testActualPhotosDecodeExportVerificationAndOfflineReopen() { realPhotosWorkflow(expectPrompt: true) }
    func testExplicitlyPreconditionedPhotosDecodeExportAndReopen() {
        print("PRECONDITIONED_SIMULATOR_PHOTOS_GRANTED: this does not qualify system prompt interaction")
        realPhotosWorkflow(expectPrompt: false)
    }
    func testPreconditionedPhotosWorkflowAtLargestPublicTrait() {
        print("PRECONDITIONED_TV_PUBLIC_TRAIT_STRESS: app rendering only, not system setting propagation")
        realPhotosWorkflow(expectPrompt: false, publicTraitStress: true)
    }
    private func traitReadback(_ payload: XCUIElement) -> (String, Double) {
        let raw = (payload.value as? String) ?? ""
        let fields = raw.split(separator: ";").map(String.init)
        guard fields.count == 2, fields[0].hasPrefix("trait="), fields[1].hasPrefix("bodyMetric="),
              let metric = Double(fields[1].dropFirst("bodyMetric=".count)), metric.isFinite, metric > 0 else {
            XCTFail("Missing actual TV trait/font readback: \(raw)"); return ("missing", 0)
        }
        return (String(fields[0].dropFirst("trait=".count)), metric)
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
    private func realPhotosWorkflow(expectPrompt: Bool, publicTraitStress: Bool = false) {
        var baselineMetric: Double = 0
        var baselineHeight: CGFloat = 0
        let viewport = app.frame
        if publicTraitStress {
            app.terminate(); app.launchEnvironment["QRCATCHER_TV_LAYOUT_PROBE"] = "1"; app.launch()
            focusAndSelect(app.buttons["tv.photos"])
            let source = app.buttons["tv.asset.0"]
            XCTAssertTrue(source.waitForExistence(timeout: 20)); focusAndSelect(source)
            let baseline = app.staticTexts["tv.payload"]
            XCTAssertTrue(baseline.waitForExistence(timeout: 20)); XCTAssertEqual(baseline.label, "QRCatcher 你好 🌈 123")
            let observation = traitReadback(baseline); XCTAssertEqual(observation.0, "baseline")
            baselineMetric = observation.1; baselineHeight = baseline.frame.height
            app.terminate()
            // A fresh synthetic history keeps every existing count/delete oracle
            // independent of the baseline measurement's genuine Photos import.
            app.launchEnvironment["QRCATCHER_TV_TEST_STORE"] = UUID().uuidString
            app.launchEnvironment["QRCATCHER_TV_LAYOUT_STRESS"] = "accessibility5"; app.launch()
            XCTAssertEqual(app.frame.width, viewport.width, accuracy: 0.5)
            XCTAssertEqual(app.frame.height, viewport.height, accuracy: 0.5)
        }
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
        if publicTraitStress {
            let observation = traitReadback(payload)
            XCTAssertEqual(observation.0, "accessibility5"); XCTAssertGreaterThan(observation.1, baselineMetric)
            XCTAssertGreaterThan(payload.frame.height, baselineHeight + 1)
            // c1552a7 reported the full AX label inside one 98-point line but
            // its actual English pixels ended in an ellipsis, hiding "123".
            // This fixed fixture at the same native viewport must wrap, not
            // merely grow one truncated line (baseline height was 68.5 points).
            XCTAssertGreaterThanOrEqual(payload.frame.height, baselineHeight * 2,
                                        "The complete largest-trait fixture must wrap beyond a single truncated line")
            XCTAssertTrue(app.frame.contains(payload.frame), "Actual largest-trait payload must be visible")
            let preview = app.images["tv.qrPreview"]
            XCTAssertTrue(preview.exists); XCTAssertTrue(app.frame.contains(preview.frame))
            XCTAssertEqual(preview.frame.width, preview.frame.height, accuracy: 1)
            let proof: [String: Any] = ["trait": observation.0, "baseline_body_metric": baselineMetric,
                "actual_body_metric": observation.1, "baseline_payload_height": Double(baselineHeight),
                "actual_payload_height": Double(payload.frame.height), "viewport_width_points": Double(app.frame.width),
                "viewport_height_points": Double(app.frame.height), "system_setting_propagation": false]
            do {
                let data = try JSONSerialization.data(withJSONObject: proof, options: .sortedKeys)
                print("TV_PUBLIC_TRAIT_PROOF " + String(decoding: data, as: UTF8.self)); fflush(stdout)
            } catch { XCTFail("Could not retain actual TV public-trait rendering proof: \(error)") }
        }
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
        focusAndSelect(record, activate: false); capture("tv-history-focused-record", focused: record)
        let remove = app.buttons["tv.deleteRecord"].firstMatch
        focusAndSelect(remove, activate: false); capture("tv-history-focused-delete", focused: remove)
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
        let historyClosed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: chineseRecord)
        XCTAssertEqual(XCTWaiter.wait(for: [historyClosed], timeout: 10), .completed,
                       "The Chinese result capture must wait for the real history sheet to dismiss")
        let resultReady = XCTNSPredicateExpectation(predicate: NSPredicate(format: "hittable == true"), object: app.buttons["tv.photos"])
        XCTAssertEqual(XCTWaiter.wait(for: [resultReady], timeout: 10), .completed)
        XCTAssertEqual(app.staticTexts["tv.payload"].label, "QRCatcher 你好 🌈 123")
        XCTAssertEqual(app.buttons["tv.photos"].label, "照片")
        if publicTraitStress {
            XCTAssertEqual(traitReadback(app.staticTexts["tv.payload"]).0, "accessibility5")
            XCTAssertTrue(app.frame.contains(app.staticTexts["tv.payload"].frame))
        }
        capture("tv-chinese-result")
        app.terminate(); app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]; app.launch()
        focusAndSelect(app.buttons["tv.history"])
        focusAndSelect(app.buttons["tv.deleteRecord"].firstMatch)
        let confirmation = app.buttons["tv.confirmDelete"]
        XCTAssertTrue(confirmation.waitForExistence(timeout: 10), app.debugDescription)
        XCUIRemote.shared.press(.menu)
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: confirmation)], timeout: 10), .completed)
        XCTAssertEqual(app.buttons.matching(identifier: "tv.record").count, 1, "Cancel must preserve the saved result")
        focusAndSelect(app.buttons["tv.deleteRecord"].firstMatch)
        focusAndSelect(confirmation)
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: app.buttons["tv.record"].firstMatch)], timeout: 10), .completed)
        app.terminate(); app.launch(); focusAndSelect(app.buttons["tv.history"])
        XCTAssertFalse(app.buttons["tv.record"].exists)
        XCTAssertTrue(app.staticTexts["No saved QR codes yet"].exists)
        capture("tv-history-after-removal")
    }
}

// Test-runner-only stop. Returning false or throwing an XCTest assertion here
// would permit the default interruption handler to approve an unknown prompt.
@MainActor private func QRStopForUnexpectedInterruption(_ alert: XCUIElement) -> Never {
    fputs("QRCATCHER_UNEXPECTED_INTERRUPTION_ABORT_BEFORE_UI_ACTION\n", stderr); fflush(stderr)
    // Do not query AX or record a throwable assertion before this stop.
    abort()
}
