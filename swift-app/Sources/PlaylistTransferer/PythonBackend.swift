import Foundation

enum BackendError: LocalizedError {
    case invalidURL
    case serverError(String)
    case unexpectedResponse

    var errorDescription: String? {
        switch self {
        case .invalidURL:              return "Invalid URL"
        case .serverError(let msg):    return msg
        case .unexpectedResponse:      return "Unexpected backend response"
        }
    }
}

@MainActor
final class PythonBackend: ObservableObject {
    @Published var isReady = false
    @Published var startupError: String?

    private var process: Process?
    private let port = 17432

    init() {
        NotificationCenter.default.addObserver(
            forName: NSNotification.Name("NSApplicationWillTerminateNotification"),
            object: nil, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in self?.stop() }
        }
    }

    func start() {
        guard !isReady, process == nil else { return }

        guard let (exe, args) = findExecutable(port: port) else {
            startupError = "Could not find backend or Python. Run from the project directory."
            return
        }

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: exe)
        proc.arguments = args

        let stdoutPipe = Pipe()
        proc.standardOutput = stdoutPipe
        proc.standardError = FileHandle.nullDevice

        do {
            try proc.run()
        } catch {
            startupError = "Failed to launch Python: \(error.localizedDescription)"
            return
        }

        self.process = proc

        // Read "READY:<port>" from stdout, then start polling /status.
        Task.detached {
            _ = stdoutPipe.fileHandleForReading.availableData // waits for first output
            for _ in 0..<30 {
                try? await Task.sleep(nanoseconds: 300_000_000)
                if let _ = try? await self.rawGET("/status") {
                    await MainActor.run { self.isReady = true }
                    return
                }
            }
            await MainActor.run {
                self.startupError = "Python backend did not start — check that .venv is set up."
            }
        }
    }

    func stop() {
        process?.terminate()
        process = nil
        isReady = false
    }

    // MARK: - API

    func getStatus() async throws -> (hasToken: Bool, hasCredentials: Bool) {
        let d = try await get("/status")
        return (d["has_token"] as? Bool ?? false, d["has_credentials"] as? Bool ?? false)
    }

    func getCredentials() async throws -> (clientId: String, clientSecret: String) {
        let d = try await get("/credentials")
        return (d["client_id"] as? String ?? "", d["client_secret"] as? String ?? "")
    }

    func saveCredentials(clientId: String, clientSecret: String) async throws {
        _ = try await post("/credentials", body: ["client_id": clientId, "client_secret": clientSecret])
    }

    func deleteCredentials() async throws {
        _ = try await delete("/credentials")
    }

    func getAuthURL(clientId: String, clientSecret: String) async throws -> String {
        let cid = clientId.urlEncoded
        let sec = clientSecret.urlEncoded
        let d = try await get("/auth/url?client_id=\(cid)&client_secret=\(sec)")
        guard let url = d["url"] as? String else { throw BackendError.unexpectedResponse }
        return url
    }

    func exchangeToken(clientId: String, clientSecret: String, redirectResponse: String) async throws {
        _ = try await post("/auth/exchange", body: [
            "client_id": clientId,
            "client_secret": clientSecret,
            "redirect_response": redirectResponse,
        ])
    }

    func fetchPlaylist(url: String) async throws -> (name: String, trackCount: Int) {
        let d = try await post("/playlist/fetch", body: ["url": url])
        guard let name  = d["name"] as? String,
              let count = d["track_count"] as? Int else { throw BackendError.unexpectedResponse }
        return (name, count)
    }

    func importPlaylist(mode: String) async throws -> ImportResult {
        let d = try await post("/playlist/import", body: ["mode": mode])
        return ImportResult(from: d)
    }

    func checkPlaylistExists(name: String) async throws -> Bool {
        let d = try await get("/playlist/exists?name=\(name.urlEncoded)")
        return d["exists"] as? Bool ?? false
    }

    // MARK: - HTTP

    private func get(_ path: String) async throws -> [String: Any] {
        try await rawGET(path) ?? { throw BackendError.unexpectedResponse }()
    }

    private func rawGET(_ path: String) async throws -> [String: Any]? {
        guard let url = URL(string: "http://127.0.0.1:\(port)\(path)") else {
            throw BackendError.invalidURL
        }
        let (data, _) = try await URLSession.shared.data(from: url)
        return try parseBody(data)
    }

    private func post(_ path: String, body: [String: Any]) async throws -> [String: Any] {
        guard let url = URL(string: "http://127.0.0.1:\(port)\(path)") else {
            throw BackendError.invalidURL
        }
        var req = URLRequest(url: url, timeoutInterval: 300)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, _) = try await URLSession.shared.data(for: req)
        return try parseBody(data)
    }

    private func delete(_ path: String) async throws -> [String: Any] {
        guard let url = URL(string: "http://127.0.0.1:\(port)\(path)") else {
            throw BackendError.invalidURL
        }
        var req = URLRequest(url: url)
        req.httpMethod = "DELETE"
        let (data, _) = try await URLSession.shared.data(for: req)
        return try parseBody(data)
    }

    private func parseBody(_ data: Data) throws -> [String: Any] {
        guard let dict = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw BackendError.unexpectedResponse
        }
        if let msg = dict["error"] as? String { throw BackendError.serverError(msg) }
        return dict
    }

    // MARK: - Discovery

    private func findExecutable(port: Int) -> (exe: String, args: [String])? {
        let fm = FileManager.default

        // Bundled .app: Resources/playlist-backend is a PyInstaller single-file binary.
        if let resources = Bundle.main.resourcePath {
            let bundled = "\(resources)/playlist-backend"
            if fm.fileExists(atPath: bundled) {
                return (bundled, ["--port", "\(port)"])
            }
        }

        // Development: find .venv python + backend.py relative to CWD.
        let cwd = fm.currentDirectoryPath
        let pythonCandidates = [
            "\(cwd)/../.venv/bin/python3",
            "\(cwd)/.venv/bin/python3",
            "/usr/bin/python3",
        ]
        let python = pythonCandidates.first { fm.fileExists(atPath: $0) } ?? "python3"

        let scriptCandidates = ["\(cwd)/../backend.py", "\(cwd)/backend.py"]
        guard let script = scriptCandidates.first(where: { fm.fileExists(atPath: $0) }) else {
            return nil
        }

        return (python, [script, "--port", "\(port)"])
    }
}

extension String {
    var urlEncoded: String {
        addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? self
    }
}
