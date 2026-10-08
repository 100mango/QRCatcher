import SwiftUI
import AppKit

@main
struct QRCatcherMacApp: App {
    @StateObject private var workspace: MacWorkspace

    init() {
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
            labelContent()
            DispatchQueue.main.async { [weak self] in self?.labelContent() }
        }
        func labelContent() {
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
}
