import SwiftUI
import AppKit

@main
struct QRCatcherMacApp: App {
    @StateObject private var workspace: MacWorkspace

    init() {
        #if DEBUG
        // BEGIN QR_MAC_STORE_CAPTURE_INIT
        MacStoreCapture.startIfEnabled()
        // END QR_MAC_STORE_CAPTURE_INIT
        #endif
        _workspace = StateObject(wrappedValue: MacWorkspace(history: MacHistory.applicationHistory()))
    }

    var body: some Scene {
        Window("QRCatcher", id: "main") {
            MacMainView(workspace: workspace, history: workspace.history)
                .frame(minWidth: 760, minHeight: 520)
                .background(MacWindowContentAccessibility())
                .onOpenURL { workspace.read(url: $0) }
                .accessibilityIdentifier("mac.sceneRoot")
        }
        .defaultSize(width: 1060, height: 700)
        .commands {
            CommandGroup(after: .newItem) {
                Button("Open Image…", action: workspace.importFile).keyboardShortcut("o")
                Button("Export QR Image…", action: workspace.exportQR).disabled(workspace.payload == nil)
                Button("Export History…", action: workspace.exportHistory)
            }
            CommandGroup(after: .pasteboard) {
                Button("Paste Image", action: workspace.pasteImage).keyboardShortcut("v", modifiers: [.command, .shift])
                Button("Copy QR Result", action: workspace.copy).keyboardShortcut("c", modifiers: [.command, .shift]).disabled(workspace.payload == nil)
            }
        }
    }
}

/// The native window's content group sits above the SwiftUI accessibility tree.
/// Give that observed AppKit container a useful label without hiding or merging
/// any of the independently accessible sidebar, result, or toolbar controls.
private struct MacWindowContentAccessibility: NSViewRepresentable {
    final class Marker: NSView {
        #if DEBUG
        private var publicMetadataObserver: MacAuditPublicMetadataObserver?
        private weak var observedMetadataWindow: NSWindow?
        func stopPublicMetadataObserver() { publicMetadataObserver?.stop(); publicMetadataObserver = nil; observedMetadataWindow = nil }
        private var reportedWindow = false
        private func describeAccessibility(_ object: Any, depth: Int = 0) {
            guard depth < 3 else { return }
            let name = String(describing: type(of: object))
            let label: String?, role: NSAccessibility.Role?, children: [Any]?
            if let view = object as? NSView {
                label = view.accessibilityLabel(); role = view.accessibilityRole(); children = view.accessibilityChildren()
            } else if let element = object as? NSAccessibilityElement {
                label = element.accessibilityLabel(); role = element.accessibilityRole(); children = element.accessibilityChildren()
            } else { print("MAC_NATIVE_AX_CLASS", depth, name); return }
            print("MAC_NATIVE_AX_HIERARCHY", depth, name, String(describing: role), String((label ?? "<nil>").prefix(120)))
            for child in (children ?? []).prefix(6) { describeAccessibility(child, depth: depth + 1) }
        }
        #endif
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            #if DEBUG
            if observedMetadataWindow !== window {
                stopPublicMetadataObserver()
                if let window { publicMetadataObserver = MacAuditPublicMetadataObserver(window: window); observedMetadataWindow = window }
            }
            #endif
            labelContent()
            DispatchQueue.main.async { [weak self] in self?.labelContent() }
        }
        func labelContent() {
            #if DEBUG
            // BEGIN QR_MAC_STORE_CAPTURE_WINDOW
            MacStoreCapture.shared?.configureExistingWindow(window)
            // END QR_MAC_STORE_CAPTURE_WINDOW
            #endif
            window?.contentView?.setAccessibilityLabel(QRL("QRCatcher workspace"))
            window?.contentView?.setAccessibilityIdentifier("mac.windowContent")
            #if DEBUG
            if !reportedWindow, let window, window.isVisible, let content = window.contentView {
                reportedWindow = true
                print("MAC_NATIVE_AX_CONTENT", String(describing: type(of: content)), String(describing: content.accessibilityIdentifier()))
                describeAccessibility(content)
                for child in (window.accessibilityChildren() ?? []).prefix(6) { describeAccessibility(child) }
            }
            #endif
        }
    }
    func makeNSView(context: Context) -> Marker {
        let marker = Marker(frame: .zero)
        marker.setAccessibilityElement(false)
        return marker
    }
    func updateNSView(_ view: Marker, context: Context) { view.labelContent() }
    static func dismantleNSView(_ view: Marker, coordinator: ()) {
        #if DEBUG
        view.stopPublicMetadataObserver()
        #endif
    }
}

#if DEBUG
// BEGIN QR_MAC_STORE_CAPTURE_HELPER
/// Controlled Store captures only; no-token and Release do not resize a window.
/// Adapted from the verified TouchColor Mac Store capture window seam.
@MainActor private final class MacStoreCapture {
    static var shared: MacStoreCapture?
    private var applied = false
    private init() {}
    static func startIfEnabled() {
        let info = ProcessInfo.processInfo
        guard shared == nil,
              let token = info.environment["QRCATCHER_MAC_STORE_CAPTURE"], UUID(uuidString: token)?.uuidString == token,
              let path = info.environment["QRCATCHER_TEST_STORE"],
              info.arguments.contains("--ui-test-store-capture"),
              info.environment["QRCATCHER_TEST_STORE_NAME"] == nil,
              info.environment["QRCATCHER_SANDBOX_PROOF"] == nil,
              info.environment["QRCATCHER_SANDBOX_FIXTURE"] == nil,
              info.environment["QRCATCHER_MAC_PUBLIC_METADATA_TOKEN"] == nil else { return }
        let store = URL(fileURLWithPath: path).standardizedFileURL
        let folder = store.deletingLastPathComponent()
        let prefix = "QRCatcherUITest-"
        guard store.lastPathComponent == "coredata.sqlite",
              folder.lastPathComponent.hasPrefix(prefix),
              UUID(uuidString: String(folder.lastPathComponent.dropFirst(prefix.count))) != nil,
              folder.deletingLastPathComponent().resolvingSymlinksInPath() ==
                  FileManager.default.temporaryDirectory.resolvingSymlinksInPath(),
              FileManager.default.fileExists(atPath: folder.path) else { return }
        shared = MacStoreCapture()
    }
    func configureExistingWindow(_ window: NSWindow?) {
        guard !applied, let window else { return }
        applied = true
        var frame = window.frame
        frame.size = NSSize(width: 1280, height: 800)
        if let screen = window.screen ?? NSScreen.main {
            let visible = screen.visibleFrame
            let scale = screen.backingScaleFactor
            if visible.width >= frame.width, visible.height >= frame.height, scale > 0 {
                let x = ((visible.midX - frame.width / 2) * scale).rounded() / scale
                let y = ((visible.midY - frame.height / 2) * scale).rounded() / scale
                frame.origin = NSPoint(x: min(max(x, visible.minX), visible.maxX - frame.width),
                                       y: min(max(y, visible.minY), visible.maxY - frame.height))
            }
        }
        window.setFrame(frame, display: true)
    }
}
// END QR_MAC_STORE_CAPTURE_HELPER
#endif
#if DEBUG
import CryptoKit

/// In-process observation only. Never qualifies or changes an audit finding.
/// Public AppKit declarations are pinned in the local source-review packet.
@MainActor
private final class MacAuditPublicMetadataObserver {
    static let boardPrefix = "QRCatcher.MacPublicMetadata."
    static let requestType = NSPasteboard.PasteboardType(rawValue: "org.qrcatcher.mac-public-metadata.request")
    static let receiptType = NSPasteboard.PasteboardType(rawValue: "org.qrcatcher.mac-public-metadata.receipt")
    static let checkpoints = [
        "testNativeWindowResizeKeepsFullActionTitles": ["mac-before-resize", "mac-minimum-window"],
        "testChineseCriticalFlow": ["mac-chinese-reopened", "mac-chinese-policy"]
    ]
    private weak var window: NSWindow?
    private var monitor: Any?
    private let token: String
    private let testCase: String
    private var requests = 0
    private var attempts = 0
    private var acceptedRequests = Set<String>()
    private var acceptedCheckpoints = Set<String>()
    private let started = ProcessInfo.processInfo.systemUptime

    init?(window: NSWindow) {
        let env = ProcessInfo.processInfo.environment
        guard MacSandboxDiagnostics.requested, MacSandboxDiagnostics.sandboxed,
              let token = env["QRCATCHER_MAC_PUBLIC_METADATA_TOKEN"],
              UUID(uuidString: token)?.uuidString == token,
              let testCase = env["QRCATCHER_MAC_PUBLIC_METADATA_CASE"], Self.checkpoints[testCase] != nil,
              window.contentView != nil else { return nil }
        self.window = window; self.token = token; self.testCase = testCase
        monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self else { return event }
            let flags: NSEvent.ModifierFlags = [.command, .option, .control, .shift]
            guard event.keyCode == 25, !event.isARepeat,
                  event.modifierFlags.intersection(.deviceIndependentFlagsMask) == flags,
                  let root = self.window, let eventWindow = event.window,
                  eventWindow === root || eventWindow === root.attachedSheet else { return event }
            self.observeIfRequested()
            return nil
        }
        if monitor == nil { return nil }
    }
    func stop() { if let monitor { NSEvent.removeMonitor(monitor) }; monitor = nil }

    private func observeIfRequested() {
        guard requests < 6, attempts < 6, let window, window.isVisible,
              MacSandboxDiagnostics.requested, MacSandboxDiagnostics.sandboxed else { return }
        attempts += 1
        let board = NSPasteboard(name: NSPasteboard.Name(rawValue: Self.boardPrefix + token))
        guard let bytes = board.data(forType: Self.requestType), bytes.count <= 1024,
              let request = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              Set(request.keys) == Set(["schema", "token", "case", "checkpoint", "sequence", "requestID", "uptime"]),
              let schemaNumber = request["schema"] as? NSNumber, CFGetTypeID(schemaNumber) != CFBooleanGetTypeID(), schemaNumber.intValue == 1, schemaNumber.doubleValue == 1, request["token"] as? String == token,
              request["case"] as? String == testCase,
              let checkpoint = request["checkpoint"] as? String,
              let allowed = Self.checkpoints[testCase], allowed.contains(checkpoint),
              let sequenceNumber = request["sequence"] as? NSNumber, CFGetTypeID(sequenceNumber) != CFBooleanGetTypeID(),
              let sequence = request["sequence"] as? Int, sequence == allowed.firstIndex(of: checkpoint)! + 1, sequence == requests + 1,
              let requestID = request["requestID"] as? String, UUID(uuidString: requestID)?.uuidString == requestID,
              !acceptedRequests.contains(requestID), !acceptedCheckpoints.contains(checkpoint),
              let timeNumber = request["uptime"] as? NSNumber, CFGetTypeID(timeNumber) != CFBooleanGetTypeID(),
              let requestTime = request["uptime"] as? Double, requestTime.isFinite,
              requestTime >= started, ProcessInfo.processInfo.systemUptime - requestTime >= 0,
              ProcessInfo.processInfo.systemUptime - requestTime <= 5 else { return }
        requests += 1; acceptedRequests.insert(requestID); acceptedCheckpoints.insert(checkpoint)
        let change = board.changeCount
        var receipt = snapshot(window: window, checkpoint: checkpoint)
        receipt.merge(["schema": 1, "token": token, "case": testCase, "checkpoint": checkpoint,
                       "sequence": sequence, "requestID": requestID, "uptime": ProcessInfo.processInfo.systemUptime,
                       "auditQualified": false, "contrastQualified": false]) { _, new in new }
        guard board.changeCount == change,
              let data = try? JSONSerialization.data(withJSONObject: receipt, options: .sortedKeys), data.count <= 32768,
              let encoded = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              typedPublicMetadataBooleans(encoded) else { return }
        // This unique named board contains hashes and bounded metadata only.
        board.clearContents(); _ = board.setData(data, forType: Self.receiptType)
    }

    private func typedPublicMetadataBooleans(_ receipt: [String: Any]) -> Bool {
        var values: [Any?] = [receipt["auditQualified"], receipt["contrastQualified"], receipt["active"]]
        for key in ["window", "attachedSheet"] {
            if let window = receipt[key] as? [String: Any] { values += [window["visible"], window["key"], window["main"]] }
        }
        for target in (receipt["targets"] as? [[String: Any]]) ?? [] {
            for key in ["wrapper", "queried"] {
                if let node = target[key] as? [String: Any] { values.append(node["enabled"]) }
            }
        }
        return values.allSatisfy { value in
            guard let number = value as? NSNumber else { return false }
            return CFGetTypeID(number) == CFBooleanGetTypeID()
        }
    }

    private struct Node {
        let object: NSAccessibilityProtocol
        let identity: ObjectIdentifier
        let path: [String]
        let root: NSWindow
        let rootKind: String
    }
    private struct Target {
        let kind: String
        let identifier: String
        let pane: String
        let expected: String
        let sheet: Bool
    }
    private func snapshot(window: NSWindow, checkpoint: String) -> [String: Any] {
        let chinese = testCase == "testChineseCriticalFlow"
        let targets = [
            Target(kind: chinese ? "fixed-unicode-payload" : "fixed-url-payload", identifier: "mac.payload", pane: "mac.pane.result", expected: chinese ? "QRCatcher 你好 🌈 123" : "https://example.com/qrcatcher?source=golden", sheet: false),
            Target(kind: "fixed-status", identifier: "mac.status", pane: "mac.pane.result", expected: chinese ? "已保存在本机" : "Result copied", sheet: false),
            Target(kind: "fixed-link-policy", identifier: "", pane: "mac.pane.result", expected: chinese ? "只有点击「在浏览器中打开」才会打开链接。" : "Links open only when you choose Open in Browser.", sheet: false),
            Target(kind: "fixed-saved-count", identifier: "", pane: "mac.pane.history", expected: chinese ? "本机已保存 1 条记录" : "1 saved on this Mac", sheet: false)
        ] + (checkpoint == "mac-chinese-policy" ? [Target(kind: "fixed-privacy-policy", identifier: "privacy.offlineBody", pane: "mac.sheet.privacy", expected: QRPrivacyText.simplifiedChinese, sheet: true)] : [])
        var nodes: [Node] = [], seen = Set<ObjectIdentifier>(), issues = Set<String>()
        var visits = 0
        func walk(_ object: Any, root: NSWindow, rootKind: String, path: [String], active: Set<ObjectIdentifier>, depth: Int) {
            guard depth <= 16 else { issues.insert("depth-limit"); return }
            guard let ax = object as? NSAccessibilityProtocol else { issues.insert("unsupported-public-node"); return }
            let identity = ObjectIdentifier(ax)
            if active.contains(identity) { issues.insert("cycle"); return }
            if seen.contains(identity) { return } // AX children and NSView subviews overlap.
            guard visits < 256 else { issues.insert("node-limit"); return }
            visits += 1; seen.insert(identity)
            let owned: Bool
            if let view = ax as? NSView { owned = view.window === root }
            else if let ownWindow = ax.accessibilityWindow() as? NSWindow { owned = ownWindow === root }
            else { owned = false }
            guard owned else { issues.insert("outside-root-or-unknown-owner"); return }
            let identifier = ax.accessibilityIdentifier() ?? ""
            let known = ["mac.windowContent", "mac.pane.result", "mac.pane.history", "mac.sheet.privacy", "mac.payload", "mac.status", "privacy.offlineBody"]
            let nextPath = path + [known.contains(identifier) ? identifier : "unidentified"]
            nodes.append(Node(object: ax, identity: identity, path: nextPath, root: root, rootKind: rootKind))
            var nextActive = active; nextActive.insert(identity)
            let children = ax.accessibilityChildren() ?? []
            if children.count > 256 { issues.insert("node-limit"); return }
            for child in children { walk(child, root: root, rootKind: rootKind, path: nextPath, active: nextActive, depth: depth + 1) }
            if let view = ax as? NSView {
                if view.subviews.count > 256 { issues.insert("node-limit"); return }
                for child in view.subviews { walk(child, root: root, rootKind: rootKind, path: nextPath, active: nextActive, depth: depth + 1) }
            }
        }
        if let content = window.contentView { walk(content, root: window, rootKind: "main-content", path: [], active: [], depth: 0) }
        else { issues.insert("missing-content") }
        let sheet = window.attachedSheet
        if let sheet, sheet.sheetParent === window, let content = sheet.contentView {
            walk(content, root: sheet, rootKind: "attached-sheet", path: [], active: [], depth: 0)
        } else if checkpoint == "mac-chinese-policy" { issues.insert("missing-attached-sheet") }
        if (checkpoint == "mac-chinese-policy") != (sheet != nil) { issues.insert("unexpected-sheet-state") }
        if finiteFrame(window.frame) == nil || window.windowNumber < 0 { issues.insert("invalid-window-frame") }
        if NSScreen.screens.count != 1 { issues.insert("screen-identity-unknown") }
        let ordered = NSApp.orderedWindows
        if ordered.count > 8 { issues.insert("window-order-limit") }
        let observations = targets.prefix(8).map { target -> [String: Any] in
            let matching = nodes.filter { node in
                node.rootKind == (target.sheet ? "attached-sheet" : "main-content") && node.path.contains(target.pane) &&
                (target.identifier.isEmpty ? stringValue(node.object) == target.expected : node.object.accessibilityIdentifier() == target.identifier)
            }
            var result: [String: Any] = ["kind": target.kind, "identifier": target.identifier, "pane": target.pane,
                                       "expectedUTF16Length": target.expected.utf16.count, "expectedSHA256": hash(target.expected),
                                       "state": "UNKNOWN", "reason": "missing-target", "matchCount": matching.count,
                                       "matchScope": "visited-owned-public-nodes", "attributedCall": "not-run"]
            guard matching.count == 1, let wrapper = matching.first else {
                if matching.count > 1 { result["reason"] = "duplicate-target" }; return result
            }
            result["wrapper"] = identityRecord(wrapper)
            var queried = wrapper
            var queryKind = "exact-wrapper"
            if stringValue(wrapper.object) != target.expected {
                // Only an absent wrapper value can defer to its exact direct
                // rendered child. A wrong/unsupported wrapper value stays unknown.
                guard wrapper.object.accessibilityValue() == nil else { result["reason"] = "wrong-value-or-frame"; return result }
                let direct = wrapper.object.accessibilityChildren() ?? []
                guard direct.count <= 256 else { result["reason"] = "node-limit"; return result }
                let rendered = direct.compactMap { child -> Node? in
                    guard let ax = child as? NSAccessibilityProtocol,
                          ax.accessibilityRole() == .staticText,
                          stringValue(ax) == target.expected else { return nil }
                    return nodes.first { $0.identity == ObjectIdentifier(ax) && $0.root === wrapper.root && $0.path.count == wrapper.path.count + 1 }
                }
                guard rendered.count == 1, let child = rendered.first else { result["reason"] = "missing-or-duplicate-rendered-child"; return result }
                queried = child; queryKind = "direct-rendered-static-text"
            }
            result["queried"] = identityRecord(queried); result["queryKind"] = queryKind
            // A visited candidate is never proof of complete traversal or global
            // uniqueness. The one observed unsupported-node issue permits only
            // its exact owned wrapper; every other issue and child route stops.
            let partial = issues == Set(["unsupported-public-node"]) && queryKind == "exact-wrapper"
            guard issues.isEmpty || partial else { result["reason"] = "incomplete-public-traversal"; return result }
            guard let value = stringValue(queried.object), value == target.expected,
                  value.utf16.count > 0, value.utf16.count <= 4096,
                  let frame = finiteFrame(queried.object.accessibilityFrame()), frame[2] > 0, frame[3] > 0,
                  queried.root.frame.contains(queried.object.accessibilityFrame()),
                  wrapper.root.frame.contains(wrapper.object.accessibilityFrame()) else { result["reason"] = "wrong-value-or-frame"; return result }
            let range = NSRange(location: 0, length: value.utf16.count)
            result["requestedRange"] = [range.location, range.length]
            result["attributedScope"] = partial ? "partial-owned-exact-wrapper" : "complete-public-traversal"
            // The synchronous public call below must return before a completed
            // result can be emitted. No receipt proves a crashed/interrupted call.
            let returned = queried.object.accessibilityAttributedString(for: range)
            guard let attributed = returned else {
                result["attributedCall"] = "completed-nil"
                result["reason"] = "unsupported-or-mismatched-attributed-string"; return result
            }
            guard attributed.length == range.length, attributed.string == value else {
                result["attributedCall"] = "completed-mismatched"
                result["reason"] = "unsupported-or-mismatched-attributed-string"; return result
            }
            result["attributedCall"] = "completed-matched"
            result["returnedUTF16Length"] = attributed.length; result["returnedSHA256"] = hash(attributed.string)
            var runs: [[String: Any]] = [], offset = 0
            while offset < attributed.length && runs.count < 16 {
                var effective = NSRange(location: 0, length: 0)
                let attributes = attributed.attributes(at: offset, effectiveRange: &effective)
                guard effective.location == offset, effective.length > 0, NSMaxRange(effective) <= attributed.length else { result["reason"] = "invalid-attribute-range"; return result }
                var metadata: [String: Any] = [:]
                for (name, key) in [("accessibilityFont", NSAttributedString.Key.accessibilityFont), ("font", .font),
                                    ("accessibilityForegroundColor", .accessibilityForegroundColor), ("foregroundColor", .foregroundColor),
                                    ("accessibilityBackgroundColor", .accessibilityBackgroundColor), ("backgroundColor", .backgroundColor)] {
                    metadata[name] = attributeRecord(attributes[key], font: name == "font" || name == "accessibilityFont")
                }
                runs.append(["range": [effective.location, effective.length], "attributes": metadata]); offset = NSMaxRange(effective)
            }
            guard offset == attributed.length else { result["reason"] = "run-limit"; return result }
            result["runs"] = runs
            result["state"] = partial ? "UNKNOWN" : "OBSERVED"
            result["reason"] = partial ? "partial-public-attributed-string" : "public-attributed-string"
            return result
        }
        return ["state": issues.isEmpty ? "OBSERVED" : "UNKNOWN", "issues": issues.sorted(), "visitedNodes": visits,
                "coordinateSpace": "AppKit-screen-bottom-left", "active": NSApp.isActive,
                "screens": NSScreen.screens.count, "screenFrame": NSScreen.screens.count == 1 ? (finiteFrame(NSScreen.screens[0].frame) as Any? ?? NSNull()) : NSNull(),
                "keyWindow": NSApp.keyWindow?.windowNumber ?? -1, "mainWindow": NSApp.mainWindow?.windowNumber ?? -1,
                "window": windowRecord(window), "attachedSheet": sheet.map { windowRecord($0) } as Any? ?? NSNull(),
                "orderedWindows": ordered.prefix(8).map { $0.windowNumber }, "targets": observations]
    }
    private func stringValue(_ ax: NSAccessibilityProtocol) -> String? {
        guard let value = ax.accessibilityValue() as? String, value.utf16.count <= 4096 else { return nil }; return value
    }
    private func hash(_ value: String) -> String { SHA256.hash(data: Data(value.utf8)).map { String(format: "%02x", $0) }.joined() }
    private func finiteFrame(_ frame: NSRect) -> [Double]? {
        let values = [Double(frame.origin.x), Double(frame.origin.y), Double(frame.width), Double(frame.height)]
        return values.allSatisfy({ $0.isFinite }) && frame.width >= 0 && frame.height >= 0 ? values : nil
    }
    private func windowRecord(_ window: NSWindow) -> [String: Any] {
        ["number": window.windowNumber, "frame": finiteFrame(window.frame) as Any? ?? NSNull(), "visible": window.isVisible,
         "key": window.isKeyWindow, "main": window.isMainWindow, "sheetParent": window.sheetParent?.windowNumber ?? -1,
         "attachedSheet": window.attachedSheet?.windowNumber ?? -1]
    }
    private func identityRecord(_ node: Node) -> [String: Any] {
        let value = stringValue(node.object)
        let role = node.object.accessibilityRole()?.rawValue ?? "AXUnknown"
        return ["role": role.utf16.count <= 64 ? role : "AXUnknown",
                "root": node.rootKind, "window": node.root.windowNumber, "path": node.path,
                "frame": finiteFrame(node.object.accessibilityFrame()) as Any? ?? NSNull(),
                "enabled": node.object.isAccessibilityEnabled(), "valueUTF16Length": value?.utf16.count ?? -1,
                "valueSHA256": value.map(hash) ?? "unknown"]
    }
    private func attributeRecord(_ value: Any?, font: Bool) -> [String: Any] {
        guard let value else { return ["state": "UNKNOWN", "type": "absent"] }
        if font, let actual = value as? NSFont, actual.pointSize.isFinite, actual.pointSize > 0, !actual.fontName.isEmpty, actual.fontName.utf16.count <= 128 {
            return ["state": "OBSERVED", "type": "NSFont", "name": actual.fontName, "pointSize": Double(actual.pointSize),
                    "traits": actual.fontDescriptor.symbolicTraits.rawValue]
        }
        if font, let dictionary = value as? NSDictionary,
           let name = dictionary[NSAccessibility.FontAttributeKey.fontName.rawValue] as? String,
           !name.isEmpty, name.utf16.count <= 128,
           let size = dictionary[NSAccessibility.FontAttributeKey.fontSize.rawValue] as? NSNumber,
           CFGetTypeID(size) != CFBooleanGetTypeID(), size.doubleValue.isFinite, size.doubleValue > 0 {
            var result: [String: Any] = ["state": "OBSERVED", "type": "AXFontDictionary", "name": name, "pointSize": size.doubleValue]
            for (field, key) in [("family", NSAccessibility.FontAttributeKey.fontFamily), ("visibleName", .visibleName)] {
                if let raw = dictionary[key.rawValue] {
                    guard let text = raw as? String, !text.isEmpty, text.utf16.count <= 128 else { return ["state": "UNKNOWN", "type": "dictionary"] }
                    result[field] = text
                }
            }
            return result
        }
        if !font {
            // NSColor has a safe Objective-C class check. Raw CF/CGColor
            // representations remain unknown; never type-query an arbitrary
            // NSObject or conditionally downcast an opaque CF object.
            if let color = value as? NSColor, color.type == .componentBased, let normalized = color.usingColorSpace(.sRGB) {
                let components = [Double(normalized.redComponent), Double(normalized.greenComponent), Double(normalized.blueComponent), Double(normalized.alphaComponent)]
                if components.allSatisfy({ $0.isFinite && $0 >= 0 && $0 <= 1 }) {
                    return ["state": "OBSERVED", "type": "sRGB", "components": components]
                }
            }
        }
        // Missing/wrong font dictionary keys, dynamic/pattern colors and every
        // unsupported public representation remain unknown.
        return ["state": "UNKNOWN", "type": value is NSDictionary ? "dictionary" : "unsupported"]
    }
}
#endif
