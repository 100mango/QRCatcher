import Foundation

/// SwiftUI/AppKit may invoke a selection binding while rendering. Defer only
/// published mutations, and use last-intent ordering rather than comparing the
/// old selection value, which would incorrectly make the first queued row win.
@MainActor
final class QRSelectionCoordinator {
    private var generation: UInt64 = 0
    func invalidate() { generation &+= 1 }
    func enqueue(_ identifier: String?, apply: @escaping @MainActor (String?) -> Void) {
        generation &+= 1
        let ticket = generation
        Task { @MainActor [weak self] in
            guard let self, self.generation == ticket else { return }
            apply(identifier)
        }
    }
}
