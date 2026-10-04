import AppKit
import SwiftUI

/// NavigationSplitView adds a native hosting group around each pane. The audit
/// identified that exact ancestor above the labeled history Outline. Label the
/// outermost accessible group inside the split pane, preserving its role and
/// children. AppKit can insert ignored glass wrappers as direct split children.
struct MacPaneAccessibility: NSViewRepresentable {
    let label: String
    let identifier: String
    final class Marker: NSView {
        var paneLabel = ""
        var paneIdentifier = ""
        #if DEBUG
        private var reported = false
        #endif
        override func viewDidMoveToSuperview() { super.viewDidMoveToSuperview(); apply() }
        override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); apply() }
        override func layout() { super.layout(); apply() }
        func apply() {
            guard window != nil, !paneLabel.isEmpty else { return }
            var ancestor = superview
            var candidate: NSView?
            for _ in 0..<32 {
                guard let view = ancestor else { return }
                if view is NSSplitView {
                    guard let candidate else { return }
                    if candidate.accessibilityLabel() != paneLabel { candidate.setAccessibilityLabel(paneLabel) }
                    if candidate.accessibilityIdentifier() != paneIdentifier { candidate.setAccessibilityIdentifier(paneIdentifier) }
                    #if DEBUG
                    if !reported {
                        reported = true
                        print("MAC_NATIVE_AX_PANE", paneIdentifier, String(describing: type(of: candidate)),
                              String(describing: candidate.accessibilityRole()), candidate.frame,
                              candidate.accessibilityLabel() ?? "<nil>")
                    }
                    #endif
                    return
                }
                if view.isAccessibilityElement(), view.accessibilityRole() == .group { candidate = view }
                ancestor = view.superview
            }
        }
    }
    func makeNSView(context: Context) -> Marker {
        let marker = Marker(frame: .zero)
        marker.setAccessibilityElement(false)
        marker.paneLabel = label; marker.paneIdentifier = identifier
        return marker
    }
    func updateNSView(_ view: Marker, context: Context) {
        view.paneLabel = label; view.paneIdentifier = identifier; view.apply()
        DispatchQueue.main.async { [weak view] in view?.apply() }
    }
}

/// Name only the presented sheet's native hosting group. Its controls remain
/// separate accessibility children with their existing labels and actions.
struct MacSheetAccessibility: NSViewRepresentable {
    let label: String
    let identifier: String
    final class Marker: NSView {
        var sheetLabel = ""
        var sheetIdentifier = ""
        override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); apply() }
        override func layout() { super.layout(); apply() }
        func apply() {
            guard let window, window.sheetParent != nil, let content = window.contentView else { return }
            if content.accessibilityLabel() != sheetLabel { content.setAccessibilityLabel(sheetLabel) }
            if content.accessibilityIdentifier() != sheetIdentifier { content.setAccessibilityIdentifier(sheetIdentifier) }
        }
    }
    func makeNSView(context: Context) -> Marker {
        let view = Marker(frame: .zero); view.setAccessibilityElement(false)
        view.sheetLabel = label; view.sheetIdentifier = identifier
        return view
    }
    func updateNSView(_ view: Marker, context: Context) {
        view.sheetLabel = label; view.sheetIdentifier = identifier; view.apply()
        DispatchQueue.main.async { [weak view] in view?.apply() }
    }
}
