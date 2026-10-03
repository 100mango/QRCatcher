import AppKit
import SwiftUI

/// NavigationSplitView adds a native hosting group around each pane. The audit
/// identified that exact ancestor above the labeled history Outline. Label the
/// direct NSSplitView child, preserving its existing role and child semantics.
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
            var child: NSView = self
            while let parent = child.superview {
                if parent is NSSplitView {
                    child.setAccessibilityLabel(paneLabel)
                    child.setAccessibilityIdentifier(paneIdentifier)
                    #if DEBUG
                    if !reported {
                        reported = true
                        print("MAC_NATIVE_AX_PANE", paneIdentifier, String(describing: type(of: child)),
                              String(describing: child.accessibilityRole()), child.frame,
                              child.accessibilityLabel() ?? "<nil>")
                    }
                    #endif
                    return
                }
                child = parent
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
    }
}
