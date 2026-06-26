import SwiftUI
import AppKit

@main
struct SigmaQuantApp: App {
    @StateObject private var vm = ChatViewModel()
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(vm)
                .frame(minWidth: 900, minHeight: 600)
                .preferredColorScheme(.dark)
                .onAppear { AppState.vm = vm }
        }
        .defaultSize(width: 1180, height: 760)
        .windowStyle(.hiddenTitleBar)
    }
}

/// Tue le back-end (et donc llama-server) à la fermeture de l'app.
final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationWillTerminate(_ notification: Notification) { AppState.vm?.shutdown() }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

enum AppState { static weak var vm: ChatViewModel? }
