import XCTest
import CoreImage
import AppKit
import CryptoKit
import Security
import Darwin

@MainActor
final class QRCatcherMacUITests: XCTestCase {
    private var app: XCUIApplication!
    private var interruptionGuard: NSObjectProtocol?
    private var folder: URL!
    private var payloadTransition: [String: Any]?
    #if DEBUG
    private var publicMetadataSession: PublicMetadataSession?
    #endif
    private var root: URL { URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent() }

    override func setUpWithError() throws {
        continueAfterFailure = false
        // Installed before any app/system-app launch and retained through teardown.
        interruptionGuard = addUIInterruptionMonitor(withDescription: "Stop before every unexpected system interruption") { alert in
            QRStopForUnexpectedInterruption(alert)
        }
        folder = FileManager.default.temporaryDirectory.appendingPathComponent("QRCatcherUITest-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        app = XCUIApplication(url: expectedApplicationURL)
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        if isSandboxedProduct {
            // The actual sandbox app chooses its OS-provided Application Support
            // container. No absolute /tmp override or broad file grant is used.
            app.launchEnvironment["QRCATCHER_TEST_STORE_NAME"] = UUID().uuidString
            app.launchEnvironment["QRCATCHER_SANDBOX_PROOF"] = "1"
            let controlURL = expectedApplicationURL.deletingLastPathComponent().appendingPathComponent("qrcatcher-boundary-control.json")
            let control = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: controlURL)) as? [String: Any])
            XCTAssertEqual(control["unsandboxed_read_control"] as? Bool, true)
            XCTAssertEqual(control["control_sandboxed"] as? Bool, false)
            XCTAssertEqual(control["control_user_id"] as? UInt32, getuid())
            XCTAssertEqual(control["file_mode"] as? Int, 0o600)
            app.launchEnvironment["QRCATCHER_SANDBOX_BOUNDARY"] = try XCTUnwrap(control["folder"] as? String)
        } else { app.launchEnvironment["QRCATCHER_TEST_STORE"] = folder.appendingPathComponent("coredata.sqlite").path }
        #if DEBUG
        preparePublicMetadataSessionIfRequested()
        #endif
        dismissObservedRealityWidgetsCrash()
        app.launch(); verifyRunningApplication()
        XCTAssertTrue(app.buttons["mac.import"].waitForExistence(timeout: 20))
    }
    override func tearDownWithError() throws {
        defer { if let interruptionGuard { removeUIInterruptionMonitor(interruptionGuard) } }

        if (testRun?.failureCount ?? 0) > 0 { print(app.debugDescription); try? screenshot("mac-failure") }
        #if DEBUG
        publicMetadataSession?.board.clearContents(); publicMetadataSession?.board.releaseGlobally(); publicMetadataSession = nil
        #endif
        app?.terminate(); if let folder { try? FileManager.default.removeItem(at: folder) }
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
        let sidebar = app.groups["mac.pane.history"], detail = app.groups["mac.pane.result"]
        XCTAssertTrue(sidebar.descendants(matching: .any).matching(identifier: "mac.history").firstMatch.exists,
                      "The labeled native pane must retain its actual accessible history child")
        XCTAssertTrue(detail.descendants(matching: .scrollView).firstMatch.exists,
                      "The labeled result pane must retain its real accessible content")
        if app.staticTexts["mac.payload"].exists { XCTAssertTrue(detail.buttons["mac.copy"].exists) }
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
    private func supportingTextLayout(locale: String, count: Int, phase: String) throws {
        let chinese = locale == "zh-Hans"
        let policy = chinese ? "只有点击「在浏览器中打开」才会打开链接。" : "Links open only when you choose Open in Browser."
        let saved = chinese ? "本机已保存 \(count) 条记录" : "\(count) saved on this Mac"
        let window = app.windows["main"]
        if phase == "minimum-long-content" {
            XCTAssertEqual(window.frame.width, 760, accuracy: 2)
            XCTAssertLessThanOrEqual(window.frame.width, 800)
            XCTAssertLessThanOrEqual(window.frame.height, 580)
        }
        let detail = app.groups["mac.pane.result"], history = app.groups["mac.pane.history"]
        let scroll = detail.scrollViews.firstMatch
        let query = detail.staticTexts.matching(NSPredicate(format: "value == %@ OR label == %@", policy, policy))
        XCTAssertEqual(query.count, 1)
        let footer = query.firstMatch
        // Native scrolling is bounded and only reveals the existing result pane.
        // It does not activate a control or invent a hit point.
        for _ in 0..<3 where !footer.isHittable || !scroll.frame.contains(footer.frame) {
            scroll.scroll(byDeltaX: 0, deltaY: -400)
        }
        let bodyFont = NSFont.preferredFont(forTextStyle: .body)
        var rows: [[String: Any]] = []
        func rect(_ value: CGRect) -> [Double] { [Double(value.minX), Double(value.minY), Double(value.width), Double(value.height)] }
        for (role, pane, text) in [("link-policy", detail, policy), ("saved-count", history, saved)] {
            let matches = pane.staticTexts.matching(NSPredicate(format: "value == %@ OR label == %@", text, text))
            XCTAssertEqual(matches.count, 1, "Exact supporting text must remain independently accessible")
            let element = matches.firstMatch
            XCTAssertTrue(element.exists); XCTAssertTrue(element.isHittable)
            XCTAssertEqual((element.value as? String) ?? element.label, text)
            let frame = element.frame
            XCTAssertTrue([frame.minX, frame.minY, frame.width, frame.height].allSatisfy { $0.isFinite })
            XCTAssertGreaterThan(frame.width, 0); XCTAssertGreaterThan(frame.height, 0)
            XCTAssertTrue(window.frame.contains(frame)); XCTAssertTrue(pane.frame.contains(frame))
            if role == "link-policy" { XCTAssertTrue(scroll.frame.contains(frame)) }
            let expected = (text as NSString).boundingRect(with: NSSize(width: frame.width, height: CGFloat.greatestFiniteMagnitude),
                options: [.usesLineFragmentOrigin, .usesFontLeading], attributes: [.font: bodyFont])
            // This is a reference font measured at the intrinsic AX width, not
            // the resolved SwiftUI font/layout proposal. Retain it diagnostically;
            // exact strings, visible containment and retained pixels are the gate.
            rows.append(["role": role, "text": text, "frame": rect(frame), "body_measurement_height": Double(expected.height),
                         "reference_body_font": bodyFont.fontName, "reference_body_point_size": Double(bodyFont.pointSize)])
        }
        let report: [String: Any] = ["locale": locale, "phase": phase, "case": name, "window": rect(window.frame), "roles": rows,
                                   "contrast_qualified": false, "reference_font_is_resolved_element_font": false,
                                   "height_proxy_used_as_acceptance": false]
        let data = try JSONSerialization.data(withJSONObject: report, options: .sortedKeys)
        XCTAssertLessThanOrEqual(data.count, 4096)
        print("MAC_SUPPORTING_TEXT_LAYOUT", String(decoding: data, as: UTF8.self))
        let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
        attachment.name = "mac-supporting-text-layout"; attachment.lifetime = .keepAlways; add(attachment)
    }

    private func retainPayloadTransition(_ value: [String: Any]) throws {
        let data = try JSONSerialization.data(withJSONObject: value, options: .sortedKeys)
        XCTAssertLessThanOrEqual(data.count, 4096)
        print("MAC_PAYLOAD_TRANSITION", String(decoding: data, as: UTF8.self))
        let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
        attachment.name = "mac-payload-transition"; attachment.lifetime = .keepAlways; add(attachment)
    }
    private func pasteLongReadabilityPayload(_ payload: String, replacing previous: String, locale: String) throws {
        let first = app.staticTexts["mac.payload"]
        let before = (first.value as? String) ?? first.label
        XCTAssertEqual(before, previous)
        XCTAssertTrue(app.buttons["mac.copy"].isHittable)
        app.buttons["mac.copy"].click()
        let copiedBefore = NSPasteboard.general.string(forType: .string)
        XCTAssertEqual(copiedBefore, previous)
        let generator = try XCTUnwrap(CIFilter(name: "CIQRCodeGenerator"))
        generator.setValue(Data(payload.utf8), forKey: "inputMessage")
        generator.setValue("M", forKey: "inputCorrectionLevel")
        let code = try XCTUnwrap(generator.outputImage).transformed(by: CGAffineTransform(scaleX: 6, y: 6))
        let cg = try XCTUnwrap(CIContext().createCGImage(code, from: code.extent))
        NSPasteboard.general.clearContents()
        XCTAssertTrue(NSPasteboard.general.writeObjects([NSImage(cgImage: cg, size: .zero)]))
        let clipboard = try XCTUnwrap(NSPasteboard.general.data(forType: .tiff))
        let raster = try XCTUnwrap(CIImage(data: clipboard))
        let detector = try XCTUnwrap(CIDetector(ofType: CIDetectorTypeQRCode, context: CIContext(), options: [CIDetectorAccuracy: CIDetectorAccuracyHigh]))
        let control = detector.features(in: raster).compactMap { ($0 as? CIQRCodeFeature)?.messageString }
        func hash(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
        payloadTransition = ["locale": locale, "phase": "prepared", "wrapper_before": before, "copy_before": copiedBefore ?? "missing",
            "expected_payload_sha256": hash(Data(payload.utf8)), "expected_payload_utf8_bytes": payload.utf8.count,
            "raster_width": cg.width, "raster_height": cg.height, "clipboard_tiff_bytes": clipboard.count,
            "clipboard_tiff_sha256": hash(clipboard), "fixture_control_exact": control == [payload],
            "full_equality_verified": false, "wrapper_identity_refresh_scope": "selectable Text only"]
        try retainPayloadTransition(try XCTUnwrap(payloadTransition))
        XCTAssertEqual(control, [payload], "Validate actual clipboard raster before invoking the product decoder")
        app.buttons["mac.paste"].click()
        let exact = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            let matches = self.app.staticTexts.matching(identifier: "mac.payload")
            guard matches.count == 1 else { return false }
            let value = matches.firstMatch
            return ((value.value as? String) ?? value.label) == payload
        }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [exact], timeout: 15), .completed)
        let value = app.staticTexts["mac.payload"]
        XCTAssertEqual((value.value as? String) ?? value.label, payload)
        XCTAssertFalse(app.buttons["mac.openWebsite"].exists)
    }
    private func verifyLongCopyAndCapture(_ payload: String, locale: String) throws {
        let window = app.windows["main"]
        let scroll = app.groups["mac.pane.result"].scrollViews.firstMatch
        let matches = app.staticTexts.matching(identifier: "mac.payload")
        XCTAssertEqual(matches.count, 1)
        guard matches.count == 1 else { return }
        let value = matches.firstMatch, copy = app.buttons["mac.copy"]
        let after = (value.value as? String) ?? value.label
        XCTAssertEqual(after, payload)
        // The observed selectable-Text wrapper is noninteractive. Resolve only
        // its one direct rendered StaticText child; never search elsewhere in
        // the pane or infer a tap target for a read-only payload.
        let children = value.children(matching: .any)
        let text = value.children(matching: .staticText)
        XCTAssertEqual(children.count, 1); XCTAssertEqual(text.count, 1)
        guard children.count == 1, text.count == 1 else { return }
        let rendered = text.firstMatch
        XCTAssertEqual(rendered.identifier, "")
        XCTAssertEqual((rendered.value as? String) ?? rendered.label, payload)
        let frame = rendered.frame
        XCTAssertTrue([frame.minX, frame.minY, frame.maxX, frame.maxY, frame.width, frame.height].allSatisfy { $0.isFinite })
        XCTAssertGreaterThan(frame.width, 0); XCTAssertGreaterThan(frame.height, 0)
        XCTAssertTrue(window.frame.contains(value.frame)); XCTAssertTrue(scroll.frame.contains(value.frame))
        XCTAssertTrue(window.frame.contains(frame)); XCTAssertTrue(scroll.frame.contains(frame))
        // The retained English child differs from its wrapper by half a point
        // at the left edge. Allow only native pixel-rounding around that same
        // wrapper; viewport containment above remains exact.
        XCTAssertTrue(value.frame.insetBy(dx: -1, dy: -1).contains(frame))
        let renderedObservation: [String: Any] = [
            "wrapper_hittable": value.isHittable, "wrapper_enabled": value.isEnabled,
            "direct_child_count": children.count, "rendered_static_text_count": text.count,
            "rendered_identifier": rendered.identifier,
            "rendered_frame": [Double(frame.minX), Double(frame.minY), Double(frame.width), Double(frame.height)],
            "wrapper_interaction_required": false, "observations_qualify_pass": false]
        XCTAssertTrue(copy.isHittable); XCTAssertTrue(copy.isEnabled)
        XCTAssertTrue(window.frame.contains(copy.frame)); XCTAssertTrue(scroll.frame.contains(copy.frame))
        copy.click()
        let copied = NSPasteboard.general.string(forType: .string)
        var report = try XCTUnwrap(payloadTransition)
        XCTAssertEqual(report["locale"] as? String, locale)
        report["phase"] = "copy-observed"
        report["wrapper_after"] = after
        report["rendered_text_observation"] = renderedObservation
        report["copy_after_sha256"] = copied.map { SHA256.hash(data: Data($0.utf8)).map { String(format: "%02x", $0) }.joined() } ?? "missing"
        report["copy_after_utf8_bytes"] = copied?.utf8.count ?? 0
        report["full_equality_verified"] = after == payload && copied == payload
        try retainPayloadTransition(report)
        XCTAssertEqual(copied, payload)
        try capturePixels("mac-minimum-long-text-" + locale)
    }

    private func establishReadabilityResizeBaseline() throws {
        // Window restoration may legitimately launch at the 760-point product
        // minimum. Establish a real larger public-XCUI baseline before testing
        // reduction; never assume .defaultSize overrides restored geometry.
        let matches = app.windows.matching(identifier: "main")
        guard matches.count == 1, NSScreen.screens.count == 1,
              app.sheets.count == 0, app.dialogs.count == 0,
              let screen = NSScreen.screens.first, screen.frame.origin == .zero else {
            XCTFail("Ambiguous window/display or active modal before resize setup")
            throw NSError(domain: "QRCatcherResizeFixture", code: 1)
        }
        let window = matches.element(boundBy: 0)
        let original = window.frame
        let display = CGRect(x: screen.frame.minX, y: 0,
                             width: screen.frame.width, height: screen.frame.height)
        // This closed single-display fixture converts public AppKit bottom-left
        // visibleFrame to XCUI's top-left screen coordinates. Dock/menu space is
        // excluded from every planned endpoint and the resulting baseline.
        let visible = CGRect(x: screen.visibleFrame.minX,
                             y: screen.frame.maxY - screen.visibleFrame.maxY,
                             width: screen.visibleFrame.width, height: screen.visibleFrame.height)
        func finite(_ frame: CGRect) -> Bool {
            [frame.minX, frame.minY, frame.maxX, frame.maxY, frame.width, frame.height].allSatisfy { $0.isFinite }
                && frame.width > 0 && frame.height > 0
        }
        let target = CGRect(x: original.minX, y: original.minY,
                            width: min(1000, visible.maxX - original.minX),
                            height: min(660, visible.maxY - original.minY))
        guard window.exists, finite(original), finite(display), finite(visible), finite(target),
              display.contains(original), display.contains(visible), visible.contains(target),
              target.width > 860, target.height > 632 else {
            XCTFail("No safe larger baseline for unchanged strict shrink assertions")
            throw NSError(domain: "QRCatcherResizeFixture", code: 2)
        }
        var gestures = 0
        if abs(original.width - target.width) > 2 {
            let right = window.coordinate(withNormalizedOffset: CGVector(dx: 1, dy: 0.5)).withOffset(CGVector(dx: -1, dy: 0))
            let end = right.withOffset(CGVector(dx: target.width - original.width, dy: 0))
            guard visible.contains(right.screenPoint), visible.contains(end.screenPoint) else {
                XCTFail("Horizontal resize setup endpoints are not safely on screen")
                throw NSError(domain: "QRCatcherResizeFixture", code: 3)
            }
            right.click(forDuration: 0.3, thenDragTo: end); gestures += 1
        }
        XCTAssertEqual(window.frame.width, target.width, accuracy: 2)
        let intermediate = window.frame
        guard matches.count == 1, app.sheets.count == 0, app.dialogs.count == 0,
              finite(intermediate), display.contains(intermediate) else {
            XCTFail("Window identity/geometry changed during resize setup")
            throw NSError(domain: "QRCatcherResizeFixture", code: 4)
        }
        if abs(intermediate.height - target.height) > 2 {
            let bottom = window.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 1)).withOffset(CGVector(dx: 0, dy: -1))
            let end = bottom.withOffset(CGVector(dx: 0, dy: target.height - intermediate.height))
            guard visible.contains(bottom.screenPoint), visible.contains(end.screenPoint) else {
                XCTFail("Vertical resize setup endpoints are not safely on screen")
                throw NSError(domain: "QRCatcherResizeFixture", code: 5)
            }
            bottom.click(forDuration: 0.3, thenDragTo: end); gestures += 1
        }
        let observed = window.frame
        XCTAssertEqual(observed.width, target.width, accuracy: 2)
        XCTAssertEqual(observed.height, target.height, accuracy: 2)
        XCTAssertGreaterThan(observed.width, 860)
        XCTAssertGreaterThan(observed.height, 632)
        XCTAssertTrue(finite(observed)); XCTAssertTrue(visible.contains(observed))
        XCTAssertLessThanOrEqual(gestures, 2)
        func rect(_ frame: CGRect) -> [Double] { [Double(frame.minX), Double(frame.minY), Double(frame.width), Double(frame.height)] }
        let observation: [String: Any] = ["original": rect(original), "target": rect(target),
                                         "observed": rect(observed), "visible": rect(visible),
                                         "public_resize_gestures": gestures, "shrink_assertions_unchanged": true]
        print("MAC_RESIZE_BASELINE " + String(decoding: try JSONSerialization.data(withJSONObject: observation, options: [.sortedKeys]), as: UTF8.self))
    }

    private func resizeToMinimumReadabilityWindow() -> CGRect {
        let window = app.windows["main"]
        let original = window.frame
        let right = window.coordinate(withNormalizedOffset: CGVector(dx: 1, dy: 0.5)).withOffset(CGVector(dx: -1, dy: 0))
        right.click(forDuration: 0.3, thenDragTo: right.withOffset(CGVector(dx: min(0, 760 - window.frame.width), dy: 0)))
        let bottom = window.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 1)).withOffset(CGVector(dx: 0, dy: -1))
        bottom.click(forDuration: 0.3, thenDragTo: bottom.withOffset(CGVector(dx: 0, dy: min(0, 520 - window.frame.height))))
        XCTAssertLessThanOrEqual(window.frame.width, 800)
        XCTAssertLessThanOrEqual(window.frame.height, 580)
        return original
    }

    private func restoreReadabilityWindow(_ original: CGRect) {
        let window = app.windows["main"]
        let right = window.coordinate(withNormalizedOffset: CGVector(dx: 1, dy: 0.5)).withOffset(CGVector(dx: -1, dy: 0))
        right.click(forDuration: 0.3, thenDragTo: right.withOffset(CGVector(dx: original.width - window.frame.width, dy: 0)))
        let bottom = window.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 1)).withOffset(CGVector(dx: 0, dy: -1))
        bottom.click(forDuration: 0.3, thenDragTo: bottom.withOffset(CGVector(dx: 0, dy: original.height - window.frame.height)))
        XCTAssertEqual(window.frame.width, original.width, accuracy: 2)
        XCTAssertEqual(window.frame.height, original.height, accuracy: 2)
    }
    #if DEBUG
    private struct PublicMetadataSession {
        let token: String
        let testCase: String
        let checkpoints: [String]
        let board: NSPasteboard
        var sequence = 0
    }
    private func preparePublicMetadataSessionIfRequested() {
        guard ProcessInfo.processInfo.environment["QRCATCHER_MAC_PUBLIC_METADATA_DIAGNOSTIC"] == "1", isSandboxedProduct else { return }
        let selections = ["testNativeWindowResizeKeepsFullActionTitles": ["mac-before-resize", "mac-minimum-window"],
                          "testChineseCriticalFlow": ["mac-chinese-reopened", "mac-chinese-policy"]]
        let parts = name.split(whereSeparator: { !$0.isLetter && !$0.isNumber && $0 != "_" }).map(String.init)
        let matches = selections.keys.filter { parts.contains($0) }
        guard matches.count == 1, let selected = matches.first, let checkpoints = selections[selected] else { return }
        let token = UUID().uuidString
        let board = NSPasteboard(name: NSPasteboard.Name(rawValue: "QRCatcher.MacPublicMetadata." + token))
        board.clearContents()
        publicMetadataSession = PublicMetadataSession(token: token, testCase: selected, checkpoints: checkpoints, board: board)
        app.launchEnvironment["QRCATCHER_MAC_PUBLIC_METADATA_TOKEN"] = token
        app.launchEnvironment["QRCATCHER_MAC_PUBLIC_METADATA_CASE"] = selected
    }
    private func collectPublicMetadataIfSelected(_ checkpoint: String) {
        guard var session = publicMetadataSession, let index = session.checkpoints.firstIndex(of: checkpoint),
              session.sequence < 6, index == session.sequence else { return }
        session.sequence += 1; publicMetadataSession = session
        let requestID = UUID().uuidString, before = ProcessInfo.processInfo.systemUptime
        let request: [String: Any] = ["schema": 1, "token": session.token, "case": session.testCase,
                                     "checkpoint": checkpoint, "sequence": session.sequence, "requestID": requestID, "uptime": before]
        var result: [String: Any] = ["schema": 1, "token": session.token, "case": session.testCase, "checkpoint": checkpoint,
                                    "sequence": session.sequence, "requestID": requestID, "auditQualified": false,
                                    "contrastQualified": false, "sameState": "UNKNOWN", "reason": "missing-or-invalid-receipt"]
        let generalBefore = NSPasteboard.general.changeCount // Scalar only; never transport clipboard contents.
        let board = session.board
        board.clearContents()
        let requestType = NSPasteboard.PasteboardType(rawValue: "org.qrcatcher.mac-public-metadata.request")
        let receiptType = NSPasteboard.PasteboardType(rawValue: "org.qrcatcher.mac-public-metadata.receipt")
        if let data = try? JSONSerialization.data(withJSONObject: request, options: .sortedKeys), data.count <= 1024,
           board.setData(data, forType: requestType) {
            let requestChange = board.changeCount
            // No polling, sleeps, new timeout or second event. This call remains
            // inside the selected case's unchanged existing XCTest allowance.
            app.typeKey("9", modifierFlags: [.command, .option, .control, .shift])
            let now = ProcessInfo.processInfo.systemUptime
            if board.changeCount > requestChange, let data = board.data(forType: receiptType), data.count <= 32768,
               let native = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               safePublicMetadataReceipt(native), native["token"] as? String == session.token,
               native["case"] as? String == session.testCase, native["checkpoint"] as? String == checkpoint,
               native["sequence"] as? Int == session.sequence, native["requestID"] as? String == requestID,
               let observed = native["uptime"] as? Double, observed.isFinite, observed >= before, observed <= now, now - before <= 5 {
                result["native"] = native
                let paired = pairedPublicMetadata(checkpoint: checkpoint, chinese: session.testCase == "testChineseCriticalFlow")
                result["paired"] = paired
                let generalUnchanged = NSPasteboard.general.changeCount == generalBefore
                result["generalChangeCountUnchanged"] = generalUnchanged
                if generalUnchanged, publicMetadataStateMatches(native, paired: paired, checkpoint: checkpoint) {
                    result["sameState"] = "OBSERVED"; result["reason"] = "bounded-public-pair"
                } else { result["reason"] = "state-or-geometry-mismatch" }
            }
        }
        // The native receipt is never a pass/exemption, including when paired.
        var encoded = try? JSONSerialization.data(withJSONObject: result, options: .sortedKeys)
        if (encoded?.count ?? 32769) > 32768 {
            result.removeValue(forKey: "native"); result.removeValue(forKey: "paired")
            result["sameState"] = "UNKNOWN"; result["reason"] = "oversized-paired-receipt"
            encoded = try? JSONSerialization.data(withJSONObject: result, options: .sortedKeys)
        }
        if let data = encoded, data.count <= 32768 {
            let evidence = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
            evidence.name = "mac-public-metadata-" + checkpoint; evidence.lifetime = .keepAlways; add(evidence)
            print("MAC_PUBLIC_METADATA_RESULT", checkpoint, result["sameState"] ?? "UNKNOWN", result["reason"] ?? "unknown")
        }
        board.clearContents()
    }
    private func pairedPublicMetadata(checkpoint: String, chinese: Bool) -> [String: Any] {
        let main = app.windows.matching(identifier: "main")
        let targets: [(String, XCUIElementQuery)] = [
            (chinese ? "fixed-unicode-payload" : "fixed-url-payload", app.groups["mac.pane.result"].staticTexts.matching(identifier: "mac.payload")),
            ("fixed-status", app.groups["mac.pane.result"].staticTexts.matching(identifier: "mac.status")),
            ("fixed-link-policy", app.groups["mac.pane.result"].staticTexts.matching(NSPredicate(format: "value == %@ OR label == %@", chinese ? "只有点击「在浏览器中打开」才会打开链接。" : "Links open only when you choose Open in Browser.", chinese ? "只有点击「在浏览器中打开」才会打开链接。" : "Links open only when you choose Open in Browser."))),
            ("fixed-saved-count", app.groups["mac.pane.history"].staticTexts.matching(NSPredicate(format: "value == %@ OR label == %@", chinese ? "本机已保存 1 条记录" : "1 saved on this Mac", chinese ? "本机已保存 1 条记录" : "1 saved on this Mac")))
        ] + (checkpoint == "mac-chinese-policy" ? [("fixed-privacy-policy", app.sheets.groups["mac.sheet.privacy"].staticTexts.matching(identifier: "privacy.offlineBody"))] : [])
        let rows: [[String: Any]] = targets.map { kind, query in
            var row: [String: Any] = ["kind": kind, "matches": query.count]
            if query.count == 1 {
                let element = query.firstMatch
                let text = (element.value as? String) ?? element.label
                if text.utf16.count <= 4096 {
                    row["valueUTF16Length"] = text.utf16.count
                    row["valueSHA256"] = SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
                    row["frame"] = metadataFrame(element.frame)
                }
            }
            return row
        }
        return ["windows": app.windows.count, "mainWindowMatches": main.count, "windowFrame": main.count == 1 ? metadataFrame(main.firstMatch.frame) : [],
                "sheets": app.sheets.count, "dialogs": app.dialogs.count, "foreground": app.state == .runningForeground,
                "coordinateSpace": "XCTest-screen-top-left", "screens": NSScreen.screens.count,
                "screenFrame": NSScreen.screens.count == 1 ? metadataFrame(NSScreen.screens[0].frame) : [], "targets": rows]
    }
    private func metadataFrame(_ frame: CGRect) -> [Double] { [Double(frame.minX), Double(frame.minY), Double(frame.width), Double(frame.height)] }
    private func publicMetadataStateMatches(_ native: [String: Any], paired: [String: Any], checkpoint: String) -> Bool {
        guard native["state"] as? String == "OBSERVED", native["active"] as? Bool == true,
              paired["coordinateSpace"] as? String == "XCTest-screen-top-left", native["coordinateSpace"] as? String == "AppKit-screen-bottom-left",
              paired["screens"] as? Int == 1, native["screens"] as? Int == 1,
              paired["windows"] as? Int == 1, paired["mainWindowMatches"] as? Int == 1,
              paired["dialogs"] as? Int == 0, paired["foreground"] as? Bool == true,
              paired["sheets"] as? Int == (checkpoint == "mac-chinese-policy" ? 1 : 0),
              let window = native["window"] as? [String: Any], let windowNumber = window["number"] as? Int, windowNumber >= 0,
              let keyWindow = native["keyWindow"] as? Int,
              let expectedKeyWindow = (checkpoint == "mac-chinese-policy" ? (native["attachedSheet"] as? [String: Any]) : window)?["number"] as? Int,
              native["mainWindow"] as? Int == windowNumber, keyWindow == expectedKeyWindow,
              let nativeFrame = window["frame"] as? [Double],
              let uiFrame = paired["windowFrame"] as? [Double], let screen = paired["screenFrame"] as? [Double],
              nativeFrame.count == 4, uiFrame.count == 4, screen.count == 4, native["screenFrame"] as? [Double] == screen,
              metadataFramesMatch(nativeFrame, ui: uiFrame, screen: screen),
              let observations = native["targets"] as? [[String: Any]], let controls = paired["targets"] as? [[String: Any]],
              observations.count == controls.count else { return false }
        for (observation, control) in zip(observations, controls) {
            guard observation["state"] as? String == "OBSERVED", observation["kind"] as? String == control["kind"] as? String,
                  control["matches"] as? Int == 1, let wrapper = observation["wrapper"] as? [String: Any],
                  let frame = wrapper["frame"] as? [Double], let ui = control["frame"] as? [Double],
                  metadataFramesMatch(frame, ui: ui, screen: screen),
                  observation["expectedUTF16Length"] as? Int == control["valueUTF16Length"] as? Int,
                  observation["expectedSHA256"] as? String == control["valueSHA256"] as? String else { return false }
        }
        return true
    }
    private func metadataFramesMatch(_ native: [Double], ui: [Double], screen: [Double]) -> Bool {
        guard native.count == 4, ui.count == 4, screen.count == 4, (native + ui + screen).allSatisfy({ $0.isFinite }), screen[0] == 0, screen[1] == 0 else { return false }
        let converted = [ui[0], screen[3] - ui[1] - ui[3], ui[2], ui[3]]
        return zip(native, converted).allSatisfy { abs($0 - $1) <= 2 }
    }
    private func strictMetadataBool(_ value: Any?, equals expected: Bool? = nil) -> Bool {
        guard let number = value as? NSNumber, CFGetTypeID(number) == CFBooleanGetTypeID() else { return false }
        return expected.map { number.boolValue == $0 } ?? true
    }
    private func safePublicMetadataReceipt(_ value: [String: Any]) -> Bool {
        let required: Set<String> = ["schema", "token", "case", "checkpoint", "sequence", "requestID", "uptime", "auditQualified", "contrastQualified", "state", "issues", "visitedNodes", "coordinateSpace", "active", "keyWindow", "mainWindow", "window", "attachedSheet", "orderedWindows", "targets", "screens", "screenFrame"]
        guard Set(value.keys) == required, value["schema"] as? Int == 1,
              strictMetadataBool(value["auditQualified"], equals: false), strictMetadataBool(value["contrastQualified"], equals: false),
              strictMetadataBool(value["active"]),
              ["OBSERVED", "UNKNOWN"].contains(value["state"] as? String ?? ""), value["coordinateSpace"] as? String == "AppKit-screen-bottom-left",
              let visited = value["visitedNodes"] as? Int, (0...256).contains(visited),
              let targets = value["targets"] as? [[String: Any]], targets.count <= 8,
              let ordered = value["orderedWindows"] as? [Int], ordered.count <= 8,
              let issues = value["issues"] as? [String], issues.count <= 12,
              issues.allSatisfy({ ["depth-limit", "cycle", "node-limit", "unsupported-public-node", "outside-root-or-unknown-owner", "missing-content", "missing-attached-sheet", "unexpected-sheet-state", "window-order-limit", "invalid-window-frame", "screen-identity-unknown"].contains($0) }) else { return false }
        // Closed JSON keys and bounded types. Portable review checks are kept
        // separate from native evidence; neither is an audit acceptance gate.
        let allowed: Set<String> = required.union(["number", "frame", "visible", "key", "main", "sheetParent", "kind", "identifier", "pane", "expectedUTF16Length", "expectedSHA256", "reason", "matchCount", "wrapper", "queried", "queryKind", "role", "root", "path", "enabled", "valueUTF16Length", "valueSHA256", "requestedRange", "returnedUTF16Length", "returnedSHA256", "runs", "range", "attributes", "accessibilityFont", "font", "accessibilityForegroundColor", "foregroundColor", "accessibilityBackgroundColor", "backgroundColor", "type", "name", "pointSize", "traits", "family", "visibleName", "components"])
        func bounded(_ object: Any, depth: Int) -> Bool {
            guard depth <= 16 else { return false }
            if let dictionary = object as? [String: Any] {
                guard dictionary.count <= 32, Set(dictionary.keys).isSubset(of: allowed) else { return false }
                for (key, value) in dictionary {
                    if ["auditQualified", "contrastQualified", "active", "visible", "key", "main", "enabled"].contains(key), !strictMetadataBool(value) { return false }
                    if ["schema", "sequence", "visitedNodes", "keyWindow", "mainWindow", "number", "sheetParent", "attachedSheet", "window", "expectedUTF16Length", "matchCount", "valueUTF16Length", "returnedUTF16Length", "pointSize", "traits", "uptime", "screens"].contains(key), value is NSNumber,
                       let number = value as? NSNumber, CFGetTypeID(number) == CFBooleanGetTypeID() { return false }
                    if ["frame", "range", "requestedRange", "components", "orderedWindows", "screenFrame"].contains(key), let array = value as? [Any] {
                        if !array.allSatisfy({ item in guard let number = item as? NSNumber else { return false }; return CFGetTypeID(number) != CFBooleanGetTypeID() && number.doubleValue.isFinite }) { return false }
                    }
                    if !bounded(value, depth: depth + 1) { return false }
                }
                return true
            }
            if let array = object as? [Any] { return array.count <= 17 && array.allSatisfy { bounded($0, depth: depth + 1) } }
            if let text = object as? String { return text.utf16.count <= 128 }
            if let number = object as? NSNumber { return number.doubleValue.isFinite }
            return object is NSNull
        }
        return bounded(value, depth: 0)
    }
    #endif

    private func capturePixels(_ name: String) throws {
        let png = XCUIScreen.main.screenshot().pngRepresentation
        let lossless = ["mac-before-resize", "mac-minimum-window", "mac-before-export", "mac-pasted-url",
                        "mac-chinese-reopened", "mac-minimum-long-text-en", "mac-minimum-long-text-zh-Hans"].contains(name)
        let data: Data
        let type: String
        if lossless {
            // These exact paired controls need native pixels for diagnosis.
            // No color conversion, crop, resize or JPEG recompression is applied.
            data = png; type = "public.png"
        } else {
            let bitmap = try XCTUnwrap(NSBitmapImageRep(data: png))
            data = try XCTUnwrap(bitmap.representation(using: .jpeg, properties: [NSBitmapImageRep.PropertyKey.compressionFactor: 0.55]))
            type = "public.jpeg"
        }
        XCTAssertLessThanOrEqual(data.count, 800 * 1024)
        let attachment = XCTAttachment(data: data, uniformTypeIdentifier: type)
        attachment.name = name; attachment.lifetime = XCTAttachment.Lifetime.keepAlways; add(attachment)
    }
    private func screenshot(_ name: String) throws {
        #if DEBUG
        collectPublicMetadataIfSelected(name)
        #endif
        try capturePixels(name)
        if name != "mac-failure" {
            print("MAC_AUDIT_BEFORE", name, "appEnabled", app.isEnabled, "windowEnabled", app.windows.firstMatch.isEnabled,
                  "sheets", app.sheets.count, "dialogs", app.dialogs.count)
            let previousFailureMode = continueAfterFailure
            continueAfterFailure = true
            defer { continueAfterFailure = previousFailureMode }
            var issueCount = 0
            var auditFailed = false
            do {
                try app.performAccessibilityAudit(for: .all) { issue in
                    issueCount += 1
                    auditFailed = true
                    let summary = String(issue.compactDescription.prefix(512))
                    // Every issue is a real failure. Bounded detail is retained
                    // separately; no audit category or element is ignored.
                    XCTFail("Accessibility audit [\(name)]: \(summary)")
                    if issueCount <= 8 {
                        let detail = String(("Checkpoint: " + name + "\n" + issue.compactDescription + "\n" + issue.detailedDescription + "\n" + (issue.element?.debugDescription ?? "no issue element")).prefix(20000))
                        print("MAC_ACCESSIBILITY_ISSUE", detail)
                        let evidence = XCTAttachment(string: detail); evidence.name = "mac-audit-element"; evidence.lifetime = .keepAlways; self.add(evidence)
                    }
                    return false
                }
            } catch {
                auditFailed = true
                // Some audit failures arrive before any issue callback. They
                // must still fail the test, while later functional checks run.
                if issueCount == 0 { XCTFail("Accessibility audit [\(name)] could not complete: \(error)") }
                print("MAC_AUDIT_FAILED", name, "reportedIssues", issueCount, error)
            }
            continueAfterFailure = previousFailureMode
            print("MAC_AUDIT_AFTER", name, "appEnabled", app.isEnabled, "windowEnabled", app.windows.firstMatch.isEnabled,
                  "sheets", app.sheets.count, "dialogs", app.dialogs.count)
            print("MAC_FUNCTIONAL_CHECKPOINT_REACHED", name, "auditFailed", auditFailed, "auditIssueCount", issueCount)
            // The defer restores fail-fast before any subsequent prerequisite,
            // output-file, persistence or other functional assertion executes.
        }
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

    private func recordFixedASCIIResult(_ phase: String, modalHistory: String) throws {
        let expected = "https://example.com/qrcatcher?source=golden"
        let footerText = "Links open only when you choose Open in Browser."
        let payload = app.staticTexts["mac.payload"]
        let footer = app.staticTexts.matching(NSPredicate(format: "value == %@ OR label == %@", footerText, footerText)).firstMatch
        let status = app.staticTexts["mac.status"]
        XCTAssertTrue(payload.exists); XCTAssertTrue(footer.exists); XCTAssertTrue(status.exists)
        XCTAssertEqual((payload.value as? String) ?? payload.label, expected)
        XCTAssertEqual((footer.value as? String) ?? footer.label, footerText)
        XCTAssertEqual((status.value as? String) ?? status.label, "Result copied")
        XCTAssertEqual(NSPasteboard.general.string(forType: .string), expected)
        XCTAssertEqual(app.sheets.count, 0); XCTAssertEqual(app.dialogs.count, 0)
        let window = app.windows["main"]
        XCTAssertTrue(window.frame.contains(payload.frame))
        XCTAssertTrue(window.frame.contains(footer.frame))
        func bounds(_ frame: CGRect) -> [String: Double] {
            ["x": Double(frame.minX), "y": Double(frame.minY), "width": Double(frame.width), "height": Double(frame.height)]
        }
        let record: [String: Any] = ["case": name, "phase": phase, "modal_history": modalHistory,
            "payload": expected, "footer": footerText, "status": "Result copied", "window": bounds(window.frame),
            "payload_frame": bounds(payload.frame), "footer_frame": bounds(footer.frame),
            "payload_hittable": payload.isHittable, "footer_hittable": footer.isHittable,
            "payload_subtree": String(payload.debugDescription.prefix(12000)),
            "footer_subtree": String(footer.debugDescription.prefix(12000))]
        let data = try JSONSerialization.data(withJSONObject: record, options: .sortedKeys)
        print("MAC_FIXED_STATE_AUDIT_CONTROL", String(decoding: data, as: UTF8.self))
    }

    func testPasteActualQRImageAndCancelExport() throws {
        let image = try XCTUnwrap(NSImage(contentsOf: root.appendingPathComponent("Tests/Fixtures/ascii.png")))
        NSPasteboard.general.clearContents()
        XCTAssertTrue(NSPasteboard.general.writeObjects([image]))
        app.buttons["mac.paste"].click()
        XCTAssertTrue(app.staticTexts["mac.payload"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.buttons["mac.openWebsite"].exists)
        XCTAssertEqual(app.state, .runningForeground)
        app.buttons["mac.copy"].click()
        try recordFixedASCIIResult("full-before-export", modalHistory: "no file panel opened in this process")
        try screenshot("mac-before-export")
        app.buttons["mac.exportQR"].click()
        app.dialogs.buttons["CancelButton"].firstMatch.click()
        XCTAssertTrue(app.buttons["mac.copy"].exists)
        app.buttons["mac.copy"].click()
        XCTAssertEqual(NSPasteboard.general.string(forType: .string), "https://example.com/qrcatcher?source=golden")
        try recordFixedASCIIResult("full-after-export-cancel", modalHistory: "one real QR export panel opened and canceled")
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
        // Exact normal File > Import command observed in Photos27 AX. Cocoa
        // menu titles are not the same field as the label predicate.
        let importMenu = photos.menuItems["_NS:1096"]
        XCTAssertTrue(importMenu.isEnabled, photos.debugDescription); importMenu.click()
        photos.typeKey("g", modifierFlags: [.command, .shift])
        let path = photos.sheets.textFields.firstMatch
        XCTAssertTrue(path.waitForExistence(timeout: 5), photos.debugDescription)
        path.typeKey("a", modifierFlags: .command); path.typeText(root.appendingPathComponent("Tests/Fixtures/unicode.png").path)
        photos.typeKey(.return, modifierFlags: [])
        let open = photos.sheets["open-panel"].buttons["OKButton"]
        XCTAssertTrue(open.waitForExistence(timeout: 5), photos.debugDescription); open.click()
        let review = photos.buttons["Review for Import"]
        if review.waitForExistence(timeout: 3) { review.click() }
        let importAll = photos.buttons["Import All New Photos"]
        if importAll.waitForExistence(timeout: 3) { importAll.click() }
        // Photos can import a single selected PNG directly from the open panel.
        // Require the actual populated library instead of inventing a mandatory
        // second review step. The grid/asset route was observed on this OS.
        let imported = photos.collectionViews["photos_collection_view"].descendants(matching: .any).matching(identifier: "mediaKind_asset").firstMatch
        XCTAssertTrue(imported.waitForExistence(timeout: 25), photos.debugDescription)
        XCTAssertFalse(photos.sheets["open-panel"].exists)
        print("PHOTOS_LIBRARY_AFTER_IMPORT:", photos.debugDescription)
        app.activate(); verifyRunningApplication()
        app.buttons["mac.photos"].click()
        print("SYSTEM_PHOTOS_PICKER_UI:", app.debugDescription)
        let image = app.images["PXGGridLayout-Info"].firstMatch
        if image.waitForExistence(timeout: 15) {
            image.click()
        } else {
            // The current OS renders the populated picker in a remote hosted
            // sheet whose children may not be bridged into the target's AX tree.
            // Record only observed identities. The observed Photos-picker helper
            // isn't an XCUIApplication and attempting that query throws before
            // the real UI fallback can run.
            let candidates = NSWorkspace.shared.runningApplications.filter {
                guard let id = $0.bundleIdentifier?.lowercased() else { return false }
                return id.hasPrefix("com.apple.") && (id.contains("photospicker") || id.contains("photosui"))
            }.prefix(6)
            for running in candidates {
                guard let identifier = running.bundleIdentifier else { continue }
                print("PHOTOS_PICKER_OBSERVED_PROCESS", identifier, running.processIdentifier,
                      running.localizedName ?? "<no name>")
            }
            do {
                // Pixel-grounded fallback from the retained 9c876a4 screenshot:
                // one imported QR at (248,242) within a 780×620 system sheet.
                // Require that exact synthetic single-photo/layout precondition;
                // do not guess coordinates for another size or populated library.
                let sheet = app.sheets.firstMatch
                XCTAssertTrue(sheet.exists, app.debugDescription)
                XCTAssertEqual(sheet.frame.width, 780, accuracy: 2)
                XCTAssertEqual(sheet.frame.height, 620, accuracy: 2)
                XCTAssertEqual(photos.collectionViews["photos_collection_view"].descendants(matching: .any).matching(identifier: "mediaKind_asset").count, 1)
                try capturePixels("mac-system-picker-before-selection")
                // Independently decode the currently rendered thumbnail too.
                // A blank, shifted, or different library must fail before click.
                let screen = try XCTUnwrap(CIImage(data: XCUIScreen.main.screenshot().pngRepresentation))
                XCTAssertEqual(screen.extent.width, 1024, accuracy: 1)
                XCTAssertEqual(screen.extent.height, 768, accuracy: 1)
                let detector = try XCTUnwrap(CIDetector(ofType: CIDetectorTypeQRCode, context: CIContext(), options: [CIDetectorAccuracy: CIDetectorAccuracyHigh]))
                let visibleCodes = detector.features(in: screen).compactMap { $0 as? CIQRCodeFeature }
                XCTAssertEqual(visibleCodes.count, 1)
                let visible = try XCTUnwrap(visibleCodes.first)
                XCTAssertEqual(visible.messageString, "QRCatcher 你好 🌈 123")
                let renderedCenter = CGPoint(x: visible.bounds.midX, y: screen.extent.height - visible.bounds.midY)
                XCTAssertEqual(renderedCenter.x, sheet.frame.minX + 248, accuracy: 15)
                XCTAssertEqual(renderedCenter.y, sheet.frame.minY + 242, accuracy: 15)
                print("PHOTOS_PICKER_PIXEL_GROUNDED_SINGLE_ASSET_SELECTION", sheet.frame)
                sheet.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: 248, dy: 242)).click()
                try capturePixels("mac-system-picker-after-selection")
            }
        }
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
        try supportingTextLayout(locale: "zh-Hans", count: 1, phase: "full")
        try screenshot("mac-chinese-reopened")
        app.buttons["mac.privacy"].click()
        let body = app.staticTexts["privacy.offlineBody"]
        XCTAssertTrue(body.waitForExistence(timeout: 5))
        let privacyGroup = app.sheets.groups["mac.sheet.privacy"]
        XCTAssertTrue(privacyGroup.exists); XCTAssertEqual(privacyGroup.label, "隐私")
        XCTAssertTrue(privacyGroup.staticTexts["privacy.offlineBody"].exists)
        XCTAssertTrue(privacyGroup.buttons["完成"].exists)
        let text = (body.value as? String) ?? body.label
        XCTAssertTrue(text.contains("本地数据可通过相应应用或系统删除，权限可在系统设置中撤回。"))
        XCTAssertTrue(text.contains("系统 iCloud 同步"))
        try screenshot("mac-chinese-policy")
        app.buttons["完成"].firstMatch.click()
        let closed = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in self.app.sheets.count == 0 && self.app.dialogs.count == 0 }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [closed], timeout: 5), .completed)
        let originalWindow = resizeToMinimumReadabilityWindow()
        let longText = String(repeating: "完整保留二维码内容，支持中文和 English，并且仍能阅读说明与保存数量。", count: 6)
        try pasteLongReadabilityPayload(longText, replacing: "QRCatcher 你好 🌈 123", locale: "zh-Hans")
        try supportingTextLayout(locale: "zh-Hans", count: 2, phase: "minimum-long-content")
        try verifyLongCopyAndCapture(longText, locale: "zh-Hans")
        restoreReadabilityWindow(originalWindow)
    }

    func testNativeWindowResizeKeepsFullActionTitles() throws {
        let image = try XCTUnwrap(NSImage(contentsOf: root.appendingPathComponent("Tests/Fixtures/ascii.png")))
        NSPasteboard.general.clearContents(); XCTAssertTrue(NSPasteboard.general.writeObjects([image]))
        app.buttons["mac.paste"].click()
        XCTAssertTrue(app.staticTexts["mac.payload"].waitForExistence(timeout: 15))
        let window = app.windows["main"]
        try establishReadabilityResizeBaseline()
        let before = window.frame
        app.buttons["mac.copy"].click()
        try recordFixedASCIIResult("full-before-resize", modalHistory: "no file panel opened in this process")
        try supportingTextLayout(locale: "en", count: 1, phase: "full")
        try screenshot("mac-before-resize")
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
        try recordFixedASCIIResult("narrow-after-resize", modalHistory: "no file panel opened in this process")
        try screenshot("mac-minimum-window")
        let longText = String(repeating: "Keep the full QR result readable alongside its safety instruction and saved-history count. ", count: 4)
        try pasteLongReadabilityPayload(longText, replacing: "https://example.com/qrcatcher?source=golden", locale: "en")
        try supportingTextLayout(locale: "en", count: 2, phase: "minimum-long-content")
        try verifyLongCopyAndCapture(longText, locale: "en")
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
        let cameraGroup = app.sheets.groups["mac.sheet.camera"]
        XCTAssertTrue(cameraGroup.exists); XCTAssertEqual(cameraGroup.label, "Camera")
        XCTAssertTrue(cameraGroup.staticTexts["mac.cameraStatus"].exists)
        XCTAssertTrue(cameraGroup.buttons["Done"].exists)
        XCTAssertFalse(app.popUpButtons["mac.cameraDevice"].exists,
                       "An absent camera list must not offer a nonexistent default camera")
        try screenshot("mac-camera-unavailable")
        app.buttons["Done"].firstMatch.click()
        app.buttons["mac.privacy"].click()
        let policy = app.staticTexts["privacy.offlineBody"]
        XCTAssertTrue(policy.waitForExistence(timeout: 5))
        let privacyGroup = app.sheets.groups["mac.sheet.privacy"]
        XCTAssertTrue(privacyGroup.exists); XCTAssertEqual(privacyGroup.label, "Privacy")
        XCTAssertTrue(privacyGroup.staticTexts["privacy.offlineBody"].exists)
        let text = (policy.value as? String) ?? policy.label
        XCTAssertTrue(text.contains("100mango@gmail.com"))
        XCTAssertTrue(text.contains("Local data can be deleted through the relevant app or system, and permissions can be revoked in system settings."))
        try screenshot("mac-english-policy")
        app.buttons["Done"].firstMatch.click()
        XCTAssertTrue(app.buttons["mac.import"].exists)
    }
}

// Test-runner-only stop. Returning false or throwing an XCTest assertion here
// would permit the default interruption handler to approve an unknown prompt.
@MainActor private func QRStopForUnexpectedInterruption(_ alert: XCUIElement) -> Never {
    fputs("QRCATCHER_UNEXPECTED_INTERRUPTION_ABORT_BEFORE_UI_ACTION\n", stderr); fflush(stderr)
    // Do not query AX or record a throwable assertion before this stop.
    abort()
}
