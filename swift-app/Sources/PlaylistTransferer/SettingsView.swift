import SwiftUI
import AppKit

struct SettingsView: View {
    @EnvironmentObject var backend: PythonBackend
    @Environment(\.dismiss) var dismiss

    @State private var clientId = ""
    @State private var clientSecret = ""
    @State private var authURL = ""
    @State private var errorMessage: String?
    @State private var isSaving = false
    @State private var showDeleteConfirm = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            Text("Settings")
                .font(.system(size: 18, weight: .semibold))
                .padding(.bottom, 20)

            // Fields
            VStack(alignment: .leading, spacing: 14) {
                FieldRow(label: "Spotify Client ID", text: $clientId)
                FieldRow(label: "Spotify Client Secret", text: $clientSecret, secure: true)
                FieldRow(
                    label: "Authorization Redirect URL",
                    text: $authURL,
                    placeholder: "Paste the full redirect URL after authorizing…"
                )
            }

            Button("Open Spotify Authorization Page →") { openAuthPage() }
                .buttonStyle(.link)
                .font(.system(size: 12))
                .padding(.top, 10)

            if let err = errorMessage {
                Text(err)
                    .font(.system(size: 12))
                    .foregroundStyle(.red)
                    .padding(.top, 8)
            }

            Spacer()

            Divider().padding(.bottom, 14)

            // Footer buttons
            HStack {
                Button("Delete All Data") { showDeleteConfirm = true }
                    .foregroundStyle(.red)
                    .buttonStyle(.bordered)

                Spacer()

                Button("Cancel") { dismiss() }
                    .buttonStyle(.bordered)
                    .keyboardShortcut(.escape)

                Button("Save") { save() }
                    .buttonStyle(.borderedProminent)
                    .disabled(isSaving)
                    .keyboardShortcut(.return)
            }
        }
        .padding(24)
        .frame(width: 480, height: 330)
        .onAppear { loadCredentials() }
        .confirmationDialog("Delete all stored data?", isPresented: $showDeleteConfirm, titleVisibility: .visible) {
            Button("Delete", role: .destructive) { deleteAll() }
        } message: {
            Text("This removes your Spotify credentials and authorization token.")
        }
    }

    private func loadCredentials() {
        Task {
            if let (id, secret) = try? await backend.getCredentials() {
                clientId = id
                clientSecret = secret
            }
        }
    }

    private func save() {
        guard !clientId.isEmpty, !clientSecret.isEmpty else {
            errorMessage = "Please enter both Client ID and Client Secret."
            return
        }
        errorMessage = nil
        isSaving = true
        Task {
            do {
                try await backend.saveCredentials(clientId: clientId, clientSecret: clientSecret)
                if !authURL.trimmingCharacters(in: .whitespaces).isEmpty {
                    try await backend.exchangeToken(
                        clientId: clientId,
                        clientSecret: clientSecret,
                        redirectResponse: authURL.trimmingCharacters(in: .whitespaces)
                    )
                }
                dismiss()
            } catch {
                errorMessage = error.localizedDescription
            }
            isSaving = false
        }
    }

    private func openAuthPage() {
        guard !clientId.isEmpty, !clientSecret.isEmpty else {
            errorMessage = "Enter Client ID and Client Secret first."
            return
        }
        errorMessage = nil
        Task {
            do {
                let urlString = try await backend.getAuthURL(clientId: clientId, clientSecret: clientSecret)
                if let url = URL(string: urlString) {
                    NSWorkspace.shared.open(url)
                }
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    private func deleteAll() {
        Task {
            try? await backend.deleteCredentials()
            clientId = ""
            clientSecret = ""
            authURL = ""
        }
    }
}

// MARK: - Field row

private struct FieldRow: View {
    let label: String
    @Binding var text: String
    var placeholder: String? = nil
    var secure: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.secondary)
            if secure {
                SecureField(placeholder ?? label, text: $text)
                    .textFieldStyle(.roundedBorder)
            } else {
                TextField(placeholder ?? label, text: $text)
                    .textFieldStyle(.roundedBorder)
            }
        }
    }
}
