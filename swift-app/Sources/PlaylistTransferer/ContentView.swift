import SwiftUI
import AppKit

struct ContentView: View {
    @EnvironmentObject var backend: PythonBackend
    @State private var screen: Screen = .main
    @State private var showSettings = false

    var body: some View {
        ZStack {
            VisualEffectBackground()
                .ignoresSafeArea()

            switch screen {
            case .main:
                MainView(screen: $screen)
                    .transition(.opacity.combined(with: .scale(scale: 0.98)))
            case .importing(let message):
                ImportingView(message: message)
                    .transition(.opacity)
            case .results(let result):
                ResultsView(result: result) { screen = .main }
                    .transition(.opacity.combined(with: .move(edge: .trailing)))
            }
        }
        .animation(.easeInOut(duration: 0.22), value: screenTag)
        .overlay(alignment: .topTrailing) {
            if case .main = screen {
                GearButton { showSettings = true }
                    .padding(14)
                    .transition(.opacity.combined(with: .scale(scale: 0.9)))
            }
        }
        .sheet(isPresented: $showSettings) {
            SettingsView()
                .environmentObject(backend)
        }
        .onAppear {
            // Make window background transparent so vibrancy shows.
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
                NSApplication.shared.windows.first.map {
                    $0.isOpaque = false
                    $0.backgroundColor = .clear
                }
            }
        }
        .alert("Startup error", isPresented: Binding(
            get: { backend.startupError != nil },
            set: { if !$0 { backend.startupError = nil } }
        )) {
            Button("OK") { backend.startupError = nil }
        } message: {
            Text(backend.startupError ?? "")
        }
    }

    private var screenTag: Int {
        switch screen {
        case .main:       return 0
        case .importing:  return 1
        case .results:    return 2
        }
    }
}

// MARK: - Visual effect background

struct VisualEffectBackground: NSViewRepresentable {
    func makeNSView(context: Context) -> NSVisualEffectView {
        let v = NSVisualEffectView()
        v.material = .sidebar
        v.blendingMode = .behindWindow
        v.state = .active
        return v
    }
    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {}
}

// MARK: - Gear button

private struct GearButton: View {
    let action: () -> Void
    @State private var isHovered = false

    var body: some View {
        Button(action: action) {
            Image(systemName: "gear")
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(.secondary)
                .frame(width: 38, height: 38)
                .background(
                    .ultraThinMaterial,
                    in: Circle()
                )
                .overlay(Circle().stroke(.quaternary, lineWidth: 0.5))
                .scaleEffect(isHovered ? 1.08 : 1.0)
                .animation(.spring(response: 0.25, dampingFraction: 0.6), value: isHovered)
        }
        .buttonStyle(.plain)
        .onHover { isHovered = $0 }
    }
}
