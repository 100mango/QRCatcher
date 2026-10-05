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
            // Keep the gesture slow and held to avoid the momentum overshoot
            // seen in run 37176649273. In run 37205686597 the 40-point drag
            // moved content 30 points, while repeated 10.25-point drags did not
            // move it at all. Include the measured 10-point activation slop
            // plus 2 points inward, rather than damping toward that dead zone.
            let above = frame.minY < top
            let overflow = above ? top - frame.minY : frame.maxY - bottom
            let movement = (above ? CGFloat(1) : -1) * min(40, max(18, overflow + 12))
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
    private func revealPayload(_ payload: XCUIElement, publicTraitStress: Bool, phase: String) -> Bool {
        XCTAssertTrue(payload.waitForExistence(timeout: 10))
        let top = app.frame.minY + 44, bottom = app.frame.maxY - 12
        guard publicTraitStress, payload.frame.height > bottom - top else { reveal(payload); return false }
        // Large text can legitimately exceed this Watch's viewport. Keep its
        // full intrinsic height and prove both edges can be scrolled into view.
        for atTop in [true, false] {
            var reached = false
            for _ in 0..<24 {
                let edge = atTop ? payload.frame.minY : payload.frame.maxY
                let goal = atTop ? top + 4 : bottom - 4
                if payload.isHittable && abs(edge - goal) <= 6 { reached = true; break }
                let delta = goal - edge
                let movement = (delta > 0 ? CGFloat(1) : -1) * min(40, max(4, abs(delta) * 0.5))
                let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: delta > 0 ? 0.65 : 0.9))
                start.press(forDuration: 0.05, thenDragTo: start.withOffset(CGVector(dx: 0, dy: movement)),
                            withVelocity: .slow, thenHoldForDuration: 0.2)
            }
            XCTAssertTrue(reached, "The full large payload's \(atTop ? "top" : "bottom") is not reachable: \(payload.debugDescription)")
            XCTAssertEqual(payload.label, "QRCatcher 你好 🌈 123")
            capture("watch-trait-\(phase)-payload-\(atTop ? "top" : "bottom")")
        }
        return true
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
        exerciseFixtureResultAndRelaunch(publicTraitStress: false)
    }
    func testFixtureResultAndRelaunchAtLargestPublicTrait() {
        exerciseFixtureResultAndRelaunch(publicTraitStress: true)
    }
    private func exerciseFixtureResultAndRelaunch(publicTraitStress: Bool) {
        app.terminate(); app.launchEnvironment["QRCATCHER_WATCH_STORE"] = "81F3B791-5049-4ED7-B88E-9684DA76DDB8"
        if publicTraitStress { app.launchEnvironment["QRCATCHER_WATCH_LAYOUT_PROBE"] = "1" }
        app.launch()
        var baselineHeight: CGFloat = 0
        var baselineMetric: Double = 0
        let nativeFrame = app.frame
        if publicTraitStress {
            let baselineRecord = app.buttons["watch.record"].firstMatch
            XCTAssertTrue(baselineRecord.waitForExistence(timeout: 20)); baselineRecord.tap()
            let baselinePayload = app.staticTexts["watch.payload"]; reveal(baselinePayload)
            XCTAssertEqual(baselinePayload.label, "QRCatcher 你好 🌈 123")
            let observation = traitReadback(baselinePayload)
            XCTAssertEqual(observation.0, "baseline")
            baselineHeight = baselinePayload.frame.height; baselineMetric = observation.1
            app.terminate(); app.launchEnvironment["QRCATCHER_WATCH_LAYOUT_STRESS"] = "accessibility5"; app.launch()
            XCTAssertEqual(app.frame.width, nativeFrame.width, accuracy: 0.5)
            XCTAssertEqual(app.frame.height, nativeFrame.height, accuracy: 0.5)
        }
        // Hosted test prepared this source photo using the genuine Watch decoder.
        // This checks offline UI/persistence, not system Photos selection.
        let record = app.buttons["watch.record"].firstMatch
        XCTAssertTrue(record.waitForExistence(timeout: 20), app.debugDescription); record.tap()
        let sourceImage = app.images["watch.source-image"]
        capture("watch-saved-preview", revealing: sourceImage)
        let payload = app.staticTexts["watch.payload"]
        let oversized = revealPayload(payload, publicTraitStress: publicTraitStress, phase: "initial")
        XCTAssertTrue(payload.waitForExistence(timeout: 10)); XCTAssertEqual(payload.label, "QRCatcher 你好 🌈 123")
        if publicTraitStress {
            let observation = traitReadback(payload)
            XCTAssertEqual(observation.0, "accessibility5")
            XCTAssertGreaterThan(observation.1, baselineMetric)
            XCTAssertGreaterThan(payload.frame.height, baselineHeight + 1,
                                 "The actual rendered payload must grow; a requested trait alone is not evidence")
            let proof: [String: Any] = ["trait": observation.0, "baseline_body_metric": baselineMetric,
                "actual_body_metric": observation.1, "baseline_payload_height": Double(baselineHeight),
                "actual_payload_height": Double(payload.frame.height), "viewport_width_points": Double(app.frame.width),
                "viewport_height_points": Double(app.frame.height), "system_setting_propagation": false]
            if let data = try? JSONSerialization.data(withJSONObject: proof, options: .sortedKeys), let text = String(data: data, encoding: .utf8) {
                print("WATCH_PUBLIC_TRAIT_PROOF " + text)
            } else { XCTFail("Could not retain actual public-trait layout measurements") }
        }
        if !oversized { capture("watch-fixture-offline-result", revealing: payload) }
        app.terminate(); app.launch()
        XCTAssertTrue(record.waitForExistence(timeout: 15)); record.tap()
        XCTAssertEqual(app.staticTexts["watch.payload"].label, "QRCatcher 你好 🌈 123")
        let oversizedReopened = revealPayload(app.staticTexts["watch.payload"], publicTraitStress: publicTraitStress, phase: "reopened")
        if !oversizedReopened { capture("watch-reopened-qr", revealing: app.staticTexts["watch.payload"]) }
        if publicTraitStress { XCTAssertEqual(traitReadback(app.staticTexts["watch.payload"]).0, "accessibility5") }
    }
    private func traitReadback(_ payload: XCUIElement) -> (String, Double) {
        let raw = (payload.value as? String) ?? ""
        let fields = raw.split(separator: ";").map(String.init)
        guard fields.count == 2, fields[0].hasPrefix("trait="), fields[1].hasPrefix("bodyMetric="),
              let metric = Double(fields[1].dropFirst("bodyMetric=".count)), metric.isFinite, metric > 0 else {
            XCTFail("Missing actual rendered SwiftUI trait/metric readback: \(raw)"); return ("missing", 0)
        }
        return (String(fields[0].dropFirst("trait=".count)), metric)
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
@MainActor final class QRCatcherWatchSettingsDiscovery: XCTestCase {
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
    private let routeTitles = ["Settings", "Display & Brightness", "Text Size"]
    private let navigationAction = "exact_element_tap"
    private func activateNavigationRow(_ app: XCUIApplication, from pane: String,
                                       to target: String, observed: ObservedNode) throws {
        let fresh = try observeNavigation(app)
        try verifyPane(pane, app, fresh)
        let row = try navigationRow(target, fresh)
        guard row.snapshot.identifier == observed.snapshot.identifier,
              row.snapshot.elementType == observed.snapshot.elementType,
              row.snapshot.frame == observed.snapshot.frame else {
            throw Stop.discovery("Navigation target moved after observation")
        }
        let element = try liveElement(app, row)
        guard element.isEnabled, !element.isSelected, emptyValue(element.value) else {
            throw Stop.discovery("Navigation target changed before activation")
        }
        try checkScreen(app)
        try checkTime()
        navigationSteps[navigationSteps.count - 1]["state"] = "activation_attempted"
        report["navigation_steps"] = navigationSteps
        phase("before_navigation_action_" + String(navigationSteps.count))
        // Already wholly onscreen and hittable; never ask XCTest to reveal a row.
        element.tap()
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
              contract["platform"] as? String == "watch",
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
        report = ["source": source, "device": device, "nonce": nonce, "platform": "watch", "settings_bundle": bundle,
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
            attachment.name = "watch-settings-discovery"; attachment.lifetime = .keepAlways; add(attachment)
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
