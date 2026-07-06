import SwiftUI
import AppKit

// Launched via `swift run` the executable has no .app bundle, so macOS treats it
// as an accessory (no Dock icon, no menu bar). Promote it to a regular app on
// launch so it behaves like a normal window'd app.
final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }
}

@main
struct ContextLensApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var model = AppModel()
    var body: some Scene {
        WindowGroup {
            RootView().environmentObject(model)
                .frame(minWidth: 900, minHeight: 560)
        }
    }
}
