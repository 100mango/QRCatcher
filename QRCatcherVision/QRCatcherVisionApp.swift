import SwiftUI

@main
struct QRCatcherVisionApp: App {
    @StateObject private var history: MacHistory
    init() {
        _history = StateObject(wrappedValue: MacHistory.applicationHistory())
    }
    var body: some Scene {
        WindowGroup {
            VisionMainView(history: history)
        }
        .defaultSize(width: 1000, height: 720)
        .windowResizability(.contentMinSize)
    }
}
