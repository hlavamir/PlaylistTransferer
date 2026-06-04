import SwiftUI
import AppKit

@main
struct PlaylistTransfererApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var backend = PythonBackend()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(backend)
                .frame(minWidth: 520, minHeight: 320)
                .onAppear { backend.start() }
        }
        .windowResizability(.contentSize)
        .defaultSize(width: 600, height: 400)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}
