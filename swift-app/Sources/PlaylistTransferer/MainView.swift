import SwiftUI
import AppKit

struct MainView: View {
    @EnvironmentObject var backend: PythonBackend
    @Binding var screen: Screen

    @State private var url = ""
    @State private var errorMessage: String?
    @FocusState private var fieldFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            Spacer()

            VStack(spacing: 24) {
                VStack(spacing: 6) {
                    Text("Playlist Transferer")
                        .font(.system(size: 24, weight: .semibold, design: .rounded))
                    Text("Spotify → Apple Music")
                        .font(.system(size: 13))
                        .foregroundStyle(.secondary)
                }

                VStack(spacing: 10) {
                    TextField("Paste Spotify playlist URL…", text: $url)
                        .textFieldStyle(.roundedBorder)
                        .font(.system(size: 15))
                        .focused($fieldFocused)
                        .onSubmit { startImport() }
                        .frame(maxWidth: 420)

                    if let err = errorMessage {
                        Text(err)
                            .font(.system(size: 12))
                            .foregroundStyle(.red)
                            .multilineTextAlignment(.center)
                            .frame(maxWidth: 420)
                    }
                }

                Button("Import Playlist") { startImport() }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(!backend.isReady || url.trimmingCharacters(in: .whitespaces).isEmpty)
                    .keyboardShortcut(.return)
            }

            Spacer()

            if !backend.isReady && backend.startupError == nil {
                HStack(spacing: 6) {
                    ProgressView().scaleEffect(0.7)
                    Text("Starting backend…")
                        .font(.system(size: 11))
                        .foregroundStyle(.tertiary)
                }
                .padding(.bottom, 14)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.horizontal, 40)
        .onAppear { fieldFocused = true }
    }

    private func startImport() {
        let trimmed = url.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty, backend.isReady else { return }
        errorMessage = nil
        screen = .importing(message: "Fetching playlist…")

        Task {
            do {
                let (hasToken, hasCreds) = try await backend.getStatus()
                guard hasCreds else {
                    errorMessage = "Open Settings (⚙) and enter your Spotify credentials first."
                    screen = .main; return
                }
                guard hasToken else {
                    errorMessage = "Open Settings (⚙) and authorize Spotify access first."
                    screen = .main; return
                }

                let (name, count) = try await backend.fetchPlaylist(url: trimmed)
                screen = .importing(message: "Matching \(count) tracks…")

                let exists = try await backend.checkPlaylistExists(name: name)
                let mode: String
                if exists {
                    mode = duplicateAlert(name: name)
                    if mode == "cancel" { screen = .main; return }
                } else {
                    mode = "new"
                }

                screen = .importing(message: "Importing into Music…")
                let result = try await backend.importPlaylist(mode: mode)
                screen = .results(result)

            } catch {
                errorMessage = error.localizedDescription
                screen = .main
            }
        }
    }

    // NSAlert runs a nested event loop so it's safe to call synchronously on main.
    private func duplicateAlert(name: String) -> String {
        let a = NSAlert()
        a.messageText = "'\(name)' already exists"
        a.informativeText = "Extend it with new tracks, replace it entirely, or cancel?"
        a.addButton(withTitle: "Extend")
        a.addButton(withTitle: "Replace")
        a.addButton(withTitle: "Cancel")
        switch a.runModal() {
        case .alertFirstButtonReturn:  return "extend"
        case .alertSecondButtonReturn: return "replace"
        default:                       return "cancel"
        }
    }
}
