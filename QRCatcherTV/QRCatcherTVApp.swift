import SwiftUI
@main
struct QRCatcherTVApp: App {
    @StateObject private var history = TVHistory.applicationHistory()
    var body: some Scene { WindowGroup { TVMainView(history: history) } }
}
