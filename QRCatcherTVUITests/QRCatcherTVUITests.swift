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
        var previousFrame: CGRect?
        var previousIdentifier: String?
        var previousDirection: XCUIRemote.Button?
        for attempt in 0..<30 {
            if target.hasFocus { if activate { XCUIRemote.shared.press(.select) }; return }
            // Reuse metadata only until this iteration performs its next remote action.
            // The next iteration resolves fresh elements and real focus again.
            let targetIdentifier = target.identifier
            let focusedCell = scope.descendants(matching: .cell).matching(NSPredicate(format: "hasFocus == true")).firstMatch
            if focusedCell.exists, !targetIdentifier.isEmpty,
               focusedCell.buttons.count == 1, focusedCell.buttons[targetIdentifier].exists {
                // Native tvOS List reports focus on the cell that owns its one
                // button. Never infer an action from a multi-button cell.
                if activate { XCUIRemote.shared.press(.select) }; return
            }
            let focusedButton = scope.descendants(matching: .button).matching(NSPredicate(format: "hasFocus == true")).firstMatch
            let focused = focusedButton.exists ? focusedButton : scope.descendants(matching: .any).matching(NSPredicate(format: "hasFocus == true")).firstMatch
            if focused.exists {
                let destination = target.frame, origin = focused.frame
                let focusedIdentifier = focused.identifier
                let focusedLabel = focused.label, targetLabel = target.label
                if focusedLabel == targetLabel && abs(destination.midX-origin.midX) < 2 && abs(destination.midY-origin.midY) < 2 {
                    // tvOS can expose nested buttons with the same frame/title;
                    // activate the actual focused child of this exact control.
                    guard focused.hasFocus else { continue }
                    if activate { XCUIRemote.shared.press(.select) }; return
                }
                // Prefer the direct row movement, including native permission
                // dialogs. If that real press leaves focus unchanged, a diagonal
                // destination may require a visible peer before moving vertically.
                var direction: XCUIRemote.Button
                if destination.minY >= origin.maxY - 1 { direction = .down }
                else if destination.maxY <= origin.minY + 1 { direction = .up }
                else { direction = destination.midX >= origin.midX ? .right : .left }
                let unchanged = previousIdentifier == focusedIdentifier && previousFrame == origin
                if unchanged, previousDirection == direction, direction == .down || direction == .up,
                   min(destination.maxX, origin.maxX) <= max(destination.minX, origin.minX) {
                    let peers = scope.descendants(matching: .button).allElementsBoundByIndex.compactMap { peer -> (element: XCUIElement, frame: CGRect)? in
                        guard peer.exists, peer.isEnabled, peer.isHittable, !peer.hasFocus else { return nil }
                        let frame = peer.frame
                        guard min(frame.maxY, origin.maxY) > max(frame.minY, origin.minY) + 1 &&
                               min(frame.maxX, destination.maxX) > max(frame.minX, destination.minX) + 1 &&
                               (frame.midX - origin.midX) * (destination.midX - origin.midX) > 0 else { return nil }
                        return (peer, frame)
                    }
                    if let bridge = peers.min(by: { abs($0.frame.midX - origin.midX) < abs($1.frame.midX - origin.midX) }) {
                        direction = bridge.frame.midX > origin.midX ? .right : .left
                        print("TV_REMOTE_FOCUS_BRIDGE", bridge.element.identifier, bridge.frame)
                    }
                }
                print("TV_REMOTE_FOCUS_STEP", attempt, focusedIdentifier, origin, "toward", targetIdentifier, destination, "press", direction)
                previousFrame = origin; previousIdentifier = focusedIdentifier; previousDirection = direction
                XCUIRemote.shared.press(direction)
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

// Explicitly selected, read-only diagnostic. It never selects a text-size value.
@MainActor final class QRCatcherTVSettingsDiscovery: XCTestCase {
    private var navigationSteps: [[String: Any]] = []
    private var focusSteps: [[String: Any]] = []
    private var lastScreenshot: XCUIScreenshot?
    private var settings: XCUIApplication?
    private var interruptionGuard: NSObjectProtocol?
    private var report: [String: Any] = [:]
    private var began = ProcessInfo.processInfo.systemUptime
    private enum Stop: Error { case discovery(String) }

    override func tearDownWithError() throws {
        defer { if let interruptionGuard { removeUIInterruptionMonitor(interruptionGuard) } }
        settings?.terminate()
    }

    private func checkTime() throws {
        guard (ProcessInfo.processInfo.systemUptime - began) < 45 else { throw Stop.discovery("Read-only observation deadline") }
    }
    private func checkScreen(_ app: XCUIApplication) throws {
        try checkTime()
        guard app.state == .runningForeground else { throw Stop.discovery("Settings is not the foreground application") }
        if app.alerts.count != 0 { QRStopForUnexpectedInterruption(app.alerts.firstMatch) }
    }
    private func phase(_ name: String) {
        let value: [String: Any] = ["phase": name, "source": report["source"] ?? "missing", "device": report["device"] ?? "missing",
            "nonce": report["nonce"] ?? "missing", "elapsed_seconds": ProcessInfo.processInfo.systemUptime - began,
            "setting_change_attempted": false]
        if let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]),
           let text = String(data: data, encoding: .utf8) { print("QRCATCHER_SETTINGS_DISCOVERY_PHASE " + text); fflush(stdout) }
    }
    private func readControls(_ app: XCUIApplication) throws -> [[String: Any]] {
        var controls: [[String: Any]] = []
        for type in [XCUIElement.ElementType.slider, .button, .staticText] {
            try checkTime()
            let elements = app.descendants(matching: type)
            for index in 0..<min(elements.count, type == .slider ? 8 : 12) {
                try checkTime()
                let element = elements.element(boundBy: index)
                controls.append(["type": type.rawValue, "identifier": String(element.identifier.prefix(64)),
                    "label": String(element.label.prefix(128)), "value": String(String(describing: element.value ?? "").prefix(128)),
                    "enabled": element.isEnabled, "selected": element.isSelected])
            }
        }
        return controls
    }
    // Route labels come from Apple's public guides, not a presumed Settings AX schema.
    // Every role, value, geometry and title is observed afresh; unknown structure stops.
    private struct ObservedNode {
        let snapshot: XCUIElementSnapshot
        let path: [Int]
        let inControl: Bool
    }
    private struct NavigationObservation {
        let appFrame: CGRect
        let nodes: [ObservedNode]
    }
    private func validFrame(_ frame: CGRect, inside bounds: CGRect) -> Bool {
        let values = [frame.minX, frame.minY, frame.maxX, frame.maxY,
                      bounds.minX, bounds.minY, bounds.maxX, bounds.maxY]
        return values.allSatisfy { $0.isFinite } && frame.width > 0 && frame.height > 0 &&
            bounds.width > 0 && bounds.height > 0 && bounds.contains(frame)
    }
    private func frameReceipt(_ frame: CGRect) -> [Double] {
        [Double(frame.minX), Double(frame.minY), Double(frame.width), Double(frame.height)]
    }
    private func emptyValue(_ value: Any?) -> Bool {
        guard let value else { return true }
        guard let text = value as? String else { return false }
        return text.isEmpty
    }
    private func isContainer(_ type: XCUIElement.ElementType) -> Bool {
        [.application, .window, .other, .scrollView, .table, .collectionView].contains(type)
    }
    private func observeNavigation(_ app: XCUIApplication) throws -> NavigationObservation {
        try checkScreen(app)
        let root = try app.snapshot()
        guard validFrame(root.frame, inside: root.frame) else { throw Stop.discovery("Invalid Settings frame") }
        var nodes: [ObservedNode] = []
        func visit(_ node: XCUIElementSnapshot, _ path: [Int], _ inControl: Bool) throws {
            try checkTime()
            guard nodes.count < 256, path.count <= 20 else { throw Stop.discovery("Settings tree exceeds navigation bound") }
            if [.alert, .sheet, .dialog].contains(node.elementType) {
                throw Stop.discovery("Unexpected modal structure; no UI action")
            }
            nodes.append(ObservedNode(snapshot: node, path: path, inControl: inControl))
            let blocksTitle = inControl || (!isContainer(node.elementType) && node.elementType != .navigationBar)
            for (index, child) in node.children.enumerated() {
                try visit(child, path + [index], blocksTitle)
            }
        }
        try visit(root, [], false)
        try checkScreen(app)
        return NavigationObservation(appFrame: root.frame, nodes: nodes)
    }
    private func whollyVisible(_ node: ObservedNode, _ observation: NavigationObservation) -> Bool {
        let frame = node.snapshot.frame
        guard validFrame(frame, inside: observation.appFrame) else { return false }
        // Hittability only proves a hit point. Require the entire element to fit
        // every observed ancestor viewport, including nested clipping containers.
        let viewports = observation.nodes.filter {
            $0.path.count < node.path.count && node.path.starts(with: $0.path) &&
                [.scrollView, .table, .collectionView].contains($0.snapshot.elementType)
        }
        guard viewports.count <= 20 else { return false }
        return viewports.allSatisfy { validFrame(frame, inside: $0.snapshot.frame) }
    }
    private func titleCandidates(_ title: String, _ observation: NavigationObservation) -> [ObservedNode] {
        // Preserve absent versus ambiguous/present. Do not discard a competing
        // title just because it is duplicated, clipped or otherwise unverifiable.
        // Prefer a semantic navigation bar; otherwise accept only standalone text
        // outside every control. A row's static label cannot verify a pane.
        let bars = observation.nodes.filter { $0.snapshot.elementType == .navigationBar && $0.snapshot.label == title }
        return bars.isEmpty ? observation.nodes.filter {
            $0.snapshot.elementType == .staticText && $0.snapshot.label == title && !$0.inControl
        } : bars
    }
    private func observedTitle(_ title: String, _ observation: NavigationObservation) throws -> ObservedNode {
        let matches = titleCandidates(title, observation)
        guard matches.count == 1, let match = matches.first,
              whollyVisible(match, observation) else {
            throw Stop.discovery("Missing, ambiguous or clipped pane title: " + title)
        }
        return match
    }
    private func liveElement(_ app: XCUIApplication, _ node: ObservedNode) throws -> XCUIElement {
        let captured = node.snapshot
        let query = app.descendants(matching: captured.elementType).matching(NSPredicate(format: "label == %@", captured.label))
        guard query.count == 1 else { throw Stop.discovery("Live control/title identity is ambiguous") }
        let element = query.element(boundBy: 0)
        guard element.exists, element.identifier == captured.identifier, element.label == captured.label,
              element.elementType == captured.elementType, element.frame == captured.frame, element.isHittable else {
            throw Stop.discovery("Control/title changed or is not hittable")
        }
        return element
    }
    private func verifyPane(_ title: String, _ app: XCUIApplication,
                            _ observation: NavigationObservation) throws {
        let heading = try observedTitle(title, observation)
        _ = try liveElement(app, heading)
        // No other documented route title may be exposed as a current pane title.
        for other in routeTitles where other != title {
            if !titleCandidates(other, observation).isEmpty {
                throw Stop.discovery("Multiple route pane titles are exposed")
            }
        }
        try checkScreen(app)
    }
    private func safeRow(_ node: ObservedNode, _ observation: NavigationObservation) throws {
        let row = node.snapshot
        guard [.button, .cell].contains(row.elementType), !node.inControl,
              row.isEnabled, !row.isSelected, emptyValue(row.value), !row.label.isEmpty,
              row.label.utf8.count <= 128, row.identifier.utf8.count <= 128,
              whollyVisible(node, observation) else {
            throw Stop.discovery("Navigation row is disabled, selected, valued, nested, unknown or offscreen")
        }
        // A button/cell that contains any interactive/unknown child is not admitted.
        // Static labels and images are allowed only with no value or selected state.
        let descendants = observation.nodes.filter { $0.path.count > node.path.count && $0.path.starts(with: node.path) }
        guard descendants.count <= 16, descendants.allSatisfy({
            [.other, .staticText, .image].contains($0.snapshot.elementType) &&
                emptyValue($0.snapshot.value) && !$0.snapshot.isSelected
        }) else { throw Stop.discovery("Navigation row contains adjustment, value or unknown descendants") }
        // Reject overlapping controls, including a separate slider/switch sibling.
        for other in observation.nodes where other.path != node.path && !other.path.starts(with: node.path) {
            let type = other.snapshot.elementType
            if !isContainer(type) && ![.navigationBar, .staticText, .image].contains(type) &&
                other.snapshot.frame.intersects(row.frame) {
                throw Stop.discovery("Another control overlaps navigation geometry")
            }
        }
    }
    private func navigationRow(_ title: String, _ observation: NavigationObservation) throws -> ObservedNode {
        let matches = observation.nodes.filter {
            [.button, .cell].contains($0.snapshot.elementType) && $0.snapshot.label == title
        }
        guard matches.count == 1, let row = matches.first else {
            throw Stop.discovery("Documented navigation row is missing or ambiguous: " + title)
        }
        try safeRow(row, observation)
        return row
    }
    private func rowReceipt(_ row: ObservedNode) -> [String: Any] {
        ["role": row.snapshot.elementType == .button ? "button" : "cell",
         "label": row.snapshot.label, "identifier": row.snapshot.identifier,
         "frame": frameReceipt(row.snapshot.frame), "value_empty": true,
         "enabled": true, "selected": false, "adjustment_descendants": false]
    }
    private func captureKnownPane(_ app: XCUIApplication, title: String) throws {
        try checkScreen(app)
        // Keep only the most recent safely observed pane; one attachment total.
        lastScreenshot = XCUIScreen.main.screenshot()
        report["screenshot_pane"] = title
        try checkTime()
        report["hierarchy"] = String(decoding: app.debugDescription.utf8.prefix(4096), as: UTF8.self)
        report["controls"] = try readControls(app)
        report["last_observed_pane"] = title
        try checkTime()
    }
    private func navigateDocumentedRoute(_ app: XCUIApplication) throws {
        var pane = routeTitles[0]
        var initial = try observeNavigation(app)
        try verifyPane(pane, app, initial)
        try captureKnownPane(app, title: pane)
        for target in routeTitles.dropFirst() {
            try checkTime()
            initial = try observeNavigation(app)
            try verifyPane(pane, app, initial)
            let row = try navigationRow(target, initial)
            _ = try liveElement(app, row)
            var entry: [String: Any] = ["from": pane, "to": target,
                "control": rowReceipt(row), "pane_frame": frameReceipt(initial.appFrame),
                "state": "observed", "action": navigationAction]
            navigationSteps.append(entry)
            report["navigation_steps"] = navigationSteps
            try activateNavigationRow(app, from: pane, to: target, observed: row)
            entry = navigationSteps[navigationSteps.count - 1]
            entry["state"] = "activation_returned"
            navigationSteps[navigationSteps.count - 1] = entry
            report["navigation_steps"] = navigationSteps
            // No retries or guessed recovery. The old title must disappear and the
            // destination must be a unique current title outside all controls.
            let destination = try observeNavigation(app)
            try verifyPane(target, app, destination)
            entry["state"] = "destination_verified"
            navigationSteps[navigationSteps.count - 1] = entry
            report["navigation_steps"] = navigationSteps
            pane = target
            phase("destination_verified_" + String(navigationSteps.count))
            try captureKnownPane(app, title: pane)
        }
        report["navigation_complete"] = true
    }
    private let routeTitles = ["Settings", "Accessibility", "Display", "Text Size"]
    private let navigationAction = "focused_remote_select"
    private var focusMoves = 0
    private func activateNavigationRow(_ app: XCUIApplication, from pane: String,
                                       to target: String, observed: ObservedNode) throws {
        var seen: Set<String> = []
        var lastDistance: CGFloat?
        while true {
            try checkTime()
            let fresh = try observeNavigation(app)
            try verifyPane(pane, app, fresh)
            let row = try navigationRow(target, fresh)
            guard row.snapshot.identifier == observed.snapshot.identifier,
                  row.snapshot.elementType == observed.snapshot.elementType else {
                throw Stop.discovery("Navigation target identity changed")
            }
            let element = try liveElement(app, row)
            let focused = fresh.nodes.filter { $0.snapshot.hasFocus }
            guard focused.count == 1, let current = focused.first else {
                throw Stop.discovery("Focus is absent or ambiguous")
            }
            try safeRow(current, fresh)
            let currentElement = try liveElement(app, current)
            guard currentElement.hasFocus, currentElement.isEnabled,
                  !currentElement.isSelected, emptyValue(currentElement.value) else {
                throw Stop.discovery("Focus changed or became a value control")
            }
            if current.path == row.path {
                guard element.hasFocus, element.isEnabled, !element.isSelected, emptyValue(element.value) else {
                    throw Stop.discovery("Exact navigation target lost focus")
                }
                try checkScreen(app)
                try checkTime()
                guard element.hasFocus else { throw Stop.discovery("Focus changed immediately before Select") }
                navigationSteps[navigationSteps.count - 1]["control"] = rowReceipt(row)
                navigationSteps[navigationSteps.count - 1]["state"] = "activation_attempted"
                report["navigation_steps"] = navigationSteps
                phase("before_navigation_action_" + String(navigationSteps.count))
                XCUIRemote.shared.press(.select)
                return
            }
            guard focusMoves < 8 else { throw Stop.discovery("Total vertical focus movement bound reached") }
            let currentFrame = current.snapshot.frame, targetFrame = row.snapshot.frame
            let sameColumn = currentFrame.minX < targetFrame.midX && currentFrame.maxX > targetFrame.midX &&
                targetFrame.minX < currentFrame.midX && targetFrame.maxX > currentFrame.midX
            let downward = currentFrame.maxY <= targetFrame.minY
            let upward = targetFrame.maxY <= currentFrame.minY
            let distance = abs(currentFrame.midY - targetFrame.midY)
            let identity = String(current.snapshot.elementType.rawValue) + "|" + current.snapshot.identifier + "|" + current.snapshot.label
            guard sameColumn, downward || upward, seen.insert(identity).inserted,
                  lastDistance == nil || distance < lastDistance! else {
                throw Stop.discovery("Focus is not a progressing unambiguous vertical path")
            }
            lastDistance = distance
            try checkScreen(app)
            try checkTime()
            guard currentElement.hasFocus else { throw Stop.discovery("Focus changed immediately before direction press") }
            focusMoves += 1
            focusSteps.append(["from": rowReceipt(current), "toward": target,
                               "pane": pane, "pane_frame": frameReceipt(fresh.appFrame),
                               "direction": downward ? "down" : "up",
                               "state": "movement_attempted"])
            report["focus_steps"] = focusSteps
            phase("before_vertical_focus_" + String(focusMoves))
            // Public momentary vertical focus input only. Re-observe actual focus
            // before any further input; never Left/Right or repeat on uncertainty.
            if downward { XCUIRemote.shared.press(.down) }
            else { XCUIRemote.shared.press(.up) }
        }
    }
    func testReadOnlyTextSizeSettingsDiscovery() throws {
        continueAfterFailure = false
        guard let raw = ProcessInfo.processInfo.environment["QRCATCHER_SETTINGS_DISCOVERY"],
              raw.utf8.count <= 4096, let data = raw.data(using: .utf8),
              let contract = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw XCTSkip("Read-only Settings discovery requires an explicit runner contract")
        }
        guard let bundle = contract["settings_bundle"] as? String, bundle.hasPrefix("com.apple."),
              let source = contract["source"] as? String, source.range(of: "^[0-9a-f]{40}$", options: .regularExpression) != nil,
              let device = contract["device"] as? String, UUID(uuidString: device) != nil,
              let nonce = contract["nonce"] as? String, UUID(uuidString: nonce) != nil,
              contract["platform"] as? String == "tv",
              contract["discovery_protocol"] as? String == "bounded-settings-navigation-v1",
              ProcessInfo.processInfo.environment["SIMULATOR_UDID"]?.uppercased() == device,
              contract["setting_change_attempted"] as? Bool == false,
              contract["system_propagation_qualified"] as? Bool == false else {
            throw Stop.discovery("Source/device/Settings discovery contract failed before launch")
        }
        guard !ProcessInfo.processInfo.environment.keys.contains(where: { $0.contains("LAYOUT_STRESS") || $0.contains("LAYOUT_PROBE") }) else {
            throw Stop.discovery("Trait override/probe is forbidden")
        }
        interruptionGuard = addUIInterruptionMonitor(withDescription: "Stop before every unexpected Settings interruption") { alert in
            QRStopForUnexpectedInterruption(alert)
        }
        report = ["source": source, "device": device, "nonce": nonce, "platform": "tv", "settings_bundle": bundle,
            "setting_change_attempted": false, "system_propagation_qualified": false,
            "original_value_restorable": false, "setting_write_authorized": false,
            "binary_source_binding_verified": false, "discovery_protocol": "bounded-settings-navigation-v1", "screenshot_attached": false,
            "navigation_complete": false, "navigation_steps": [], "focus_steps": []]
        let app = XCUIApplication(bundleIdentifier: bundle)
        settings = app; began = ProcessInfo.processInfo.systemUptime
        phase("before_settings_launch")
        do {
            app.launch()
            phase("settings_launch_returned")
            try navigateDocumentedRoute(app)
            report["status"] = "settings_screen_observed"
        } catch {
            report["status"] = "observation_stopped"
            report["reason"] = String(String(describing: error).prefix(512))
        }
        // Only verified navigation may have occurred; no size value was selected.
        // Attach only the last previously captured safe pane. No AX work on stop.
        if let lastScreenshot {
            let attachment = XCTAttachment(screenshot: lastScreenshot)
            attachment.name = "tv-settings-discovery"; attachment.lifetime = .keepAlways; add(attachment)
            report["screenshot_attached"] = true
        }
        // A captured value is a candidate for later review, not restoration proof.
        // No further AX/screenshot query after a stopped phase. Emit known facts.
        var encoded = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
        if encoded.count > 24 * 1024 {
            report.removeValue(forKey: "controls"); report.removeValue(forKey: "hierarchy")
            report["status"] = "observation_stopped"; report["reason"] = "Observation exceeds bounded receipt cap"
            encoded = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
        }
        guard encoded.count <= 24 * 1024, let line = String(data: encoded, encoding: .utf8) else {
            throw Stop.discovery("Read-only Settings receipt exceeded cap")
        }
        print("QRCATCHER_SETTINGS_DISCOVERY " + line); fflush(stdout)
    }
}
