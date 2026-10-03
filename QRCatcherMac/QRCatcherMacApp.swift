import SwiftUI
import AppKit

@main
struct QRCatcherMacApp: App {
    @StateObject private var workspace: MacWorkspace

    init() {
        // An unavailable directory must show an error, never switch silently to an empty store.
        let url: URL
        do { url = try MacHistory.defaultURL() }
        catch { url = URL(fileURLWithPath: "/QRCatcher-unavailable/coredata.sqlite") }
        _workspace = StateObject(wrappedValue: MacWorkspace(history: MacHistory(url: url)))
    }

    var body: some Scene {
        Window("QRCatcher", id: "main") {
            MacMainView(workspace: workspace, history: workspace.history)
                .frame(minWidth: 760, minHeight: 520)
                .onOpenURL { workspace.read(url: $0) }
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
