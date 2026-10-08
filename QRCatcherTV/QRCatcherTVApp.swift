import SwiftUI
@main
struct QRCatcherTVApp: App {
    @StateObject private var history = TVHistory.applicationHistory()
    var body: some Scene {
        WindowGroup {
            #if DEBUG
            if ProcessInfo.processInfo.environment["QRCATCHER_TV_LAYOUT_STRESS"] == "accessibility5" {
                TVMainView(history: history).dynamicTypeSize(.accessibility5)
            } else { TVMainView(history: history) }
            #else
            TVMainView(history: history)
            #endif
        }
    }
}
