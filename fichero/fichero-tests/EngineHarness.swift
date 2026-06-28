//
//  EngineHarness.swift
//  FicheroTests
//
//  Connect-or-spawn a Fichero engine pointed at a freshly seeded, DISPOSABLE
//  test library, so app<->engine integration tests run *live* without ever
//  touching a real library.
//
//  Behaviour (what Daniel asked for):
//   - If an engine is already healthy on 127.0.0.1:8765, reuse it. The library
//     is selected per-request via the X-Fichero-Library-Path header, so the
//     running app's own library is never touched — we just point requests at
//     our temp .fichero. Auth is handled transparently by AuthTokenMiddleware.
//   - Otherwise spawn `uvicorn fichero.api.main:app` ourselves, with
//     FICHERO_DISABLE_AUTH=1 and an isolated FICHERO_BASE_PATH so the spawned
//     engine can't lock-fight the app's shared DuckDB.
//
//  The seeded library is built fresh each run by the Python seeder
//  (fichero-engine/scripts/seed_test_library.py) — the SAME fixture the Python
//  contract walker uses — so both ends of the contract walk identical data.
//

import FicheroAPIClient
import Foundation

/// A global handle to a spawned engine so an atexit hook can guarantee no
/// orphaned uvicorn survives the test process. Plain globals because the C
/// `atexit` callback can't capture context.
nonisolated(unsafe) private var _spawnedEngineProcess: Process?
nonisolated(unsafe) private var _atexitRegistered = false

private func _terminateSpawnedEngineAtExit() {
    _spawnedEngineProcess?.terminate()
    _spawnedEngineProcess = nil
}

@MainActor
enum EngineHarness {
    struct LiveEngine {
        let client: FicheroClient
        let libraryPath: String
        /// Ground-truth counts the seeder read back from the library (derived,
        /// not hand-declared). The test asserts the engine's over-HTTP counts
        /// equal these.
        let expected: [String: Int]
        /// Seeded row ids by name (e.g. "collection", "doc_letter") so the test
        /// references rows by name, never by a hardcoded id.
        let ids: [String: String]
        /// True if we spawned the engine ourselves (vs reusing a running one).
        let spawned: Bool
    }

    enum HarnessError: Error, CustomStringConvertible {
        case repoRootNotFound
        case seedFailed(String)
        case engineUnavailable(String)

        var description: String {
            switch self {
            case .repoRootNotFound:
                return "Could not locate the repo root (set FICHERO_REPO_ROOT)."
            case .seedFailed(let message): return "Seeding the test library failed: \(message)"
            case .engineUnavailable(let message): return "No engine and could not spawn one: \(message)"
            }
        }
    }

    /// Cached so the (expensive) spawn happens once per test process.
    private static var cached: LiveEngine?

    private static let baseURL = URL(string: "https://127.0.0.1:8765")!

    /// Returns a live engine pointed at a freshly seeded test library.
    /// Reuses a running engine if present, else spawns one. Throws if neither
    /// is possible (callers should `try` and skip on failure).
    static func live() async throws -> LiveEngine {
        if let cached { return cached }

        guard let repo = repoRoot() else { throw HarnessError.repoRootNotFound }

        // Fresh, disposable library under the OS temp dir (an allowed root in
        // the engine's path validation: /var/folders is permitted).
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("fichero-itest-\(UUID().uuidString)", isDirectory: true)
        let libURL = tempDir.appendingPathComponent("library.fichero")
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)

        let (expected, ids) = try seedLibrary(at: libURL, repo: repo)

        // Reuse a running engine if healthy; else spawn one.
        var spawned = false
        if await isHealthy(baseURL) == false {
            try spawnEngine(repo: repo, libraryPath: libURL.path)
            spawned = true
            guard await waitForHealth(baseURL, timeout: 30) else {
                throw HarnessError.engineUnavailable("spawned engine never became healthy on \(baseURL)")
            }
        }

        // When reusing a running engine, the XCTest host sandbox may redirect
        // applicationSupportDirectory to a container path that differs from where
        // the engine wrote its token. Read the token via homeDirectoryForCurrentUser
        // (which bypasses sandbox path translation, matching Python's Path.home())
        // and export it as FICHERO_AUTH_TOKEN so AuthTokenMiddleware picks it up.
        // Only inject when not already set (respects CI overrides) and not spawned
        // (spawned engines run with FICHERO_DISABLE_AUTH=1, no token needed).
        if !spawned, ProcessInfo.processInfo.environment["FICHERO_AUTH_TOKEN"] == nil,
           let token = readEngineToken() {
            setenv("FICHERO_AUTH_TOKEN", token, 1)
        }

        let client = FicheroClient(baseURL: baseURL, libraryPath: libURL.path)
        let engine = LiveEngine(
            client: client, libraryPath: libURL.path,
            expected: expected, ids: ids, spawned: spawned
        )
        cached = engine
        return engine
    }

    // MARK: - Seeding

    private static func seedLibrary(at libURL: URL, repo: URL) throws -> ([String: Int], [String: String]) {
        let venvPython = repo.appendingPathComponent(".venv/bin/python")
        let seeder = repo.appendingPathComponent("fichero-engine/scripts/seed_test_library.py")

        let proc = Process()
        proc.executableURL = venvPython
        proc.arguments = [seeder.path, libURL.path]
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = repo.appendingPathComponent("fichero-engine/src").path
        proc.environment = env
        let out = Pipe()
        proc.standardOutput = out
        proc.standardError = Pipe()
        do {
            try proc.run()
        } catch {
            throw HarnessError.seedFailed("could not launch seeder: \(error)")
        }
        proc.waitUntilExit()
        let data = out.fileHandleForReading.readDataToEndOfFile()
        guard proc.terminationStatus == 0,
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let expected = json["expected"] as? [String: Int],
              let keys = json["keys"] as? [String: String]
        else {
            throw HarnessError.seedFailed("exit \(proc.terminationStatus); output: \(String(data: data, encoding: .utf8) ?? "<none>")")
        }
        return (expected, keys)
    }

    // MARK: - Spawn

    private static func spawnEngine(repo: URL, libraryPath: String) throws {
        let uvicorn = repo.appendingPathComponent(".venv/bin/uvicorn")
        let tlsMaterial = try prepareTLSMaterial(repo: repo)
        try RemoteCertificatePinning.persistSPKIPin(tlsMaterial.spkiPin, hostString: baseURL.absoluteString)

        let proc = Process()
        proc.executableURL = uvicorn
        proc.arguments = [
            "fichero.api.main:app",
            "--port", "8765",
            "--ssl-certfile", tlsMaterial.certificatePath,
            "--ssl-keyfile", tlsMaterial.keyPath
        ]
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = repo.appendingPathComponent("fichero-engine/src").path
        env["FICHERO_DISABLE_AUTH"] = "1"
        env["FICHERO_TLS_CERTFILE"] = tlsMaterial.certificatePath
        env["FICHERO_TLS_KEYFILE"] = tlsMaterial.keyPath
        env["FICHERO_TLS_SPKI_HASH"] = tlsMaterial.spkiPin
        // Isolate the app DB so we never lock-fight the real one.
        env["FICHERO_BASE_PATH"] = repo
            .appendingPathComponent("fichero-engine").path + "/.itest-base"
        // The engine watches this PID and self-terminates if it dies. atexit
        // is unreliable when the test process is SIGKILL'd (or crashes before
        // the C handler runs), which orphans the engine on :8765 and then
        // collides with the next app/test launch. This is the robust backstop.
        env["FICHERO_PARENT_PID"] = String(ProcessInfo.processInfo.processIdentifier)
        proc.environment = env
        proc.standardOutput = Pipe()
        proc.standardError = Pipe()
        do {
            try proc.run()
        } catch {
            throw HarnessError.engineUnavailable("could not launch uvicorn: \(error)")
        }
        _spawnedEngineProcess = proc
        if !_atexitRegistered {
            atexit(_terminateSpawnedEngineAtExit)
            _atexitRegistered = true
        }
    }

    private struct HarnessTLSMaterial: Decodable {
        let certificatePath: String
        let keyPath: String
        let spkiPin: String

        enum CodingKeys: String, CodingKey {
            case certificatePath = "certificate_path"
            case keyPath = "key_path"
            case spkiPin = "spki_pin"
        }
    }

    private static func prepareTLSMaterial(repo: URL) throws -> HarnessTLSMaterial {
        let python = repo.appendingPathComponent(".venv/bin/python")
        let process = Process()
        process.executableURL = python
        process.arguments = [
            "-c",
            """
            from fichero.remote_access_tls import material_manifest_json, prepare_remote_access_tls
            print(material_manifest_json(prepare_remote_access_tls("https://127.0.0.1:8765", allow_loopback=True)))
            """
        ]
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = repo.appendingPathComponent("fichero-engine/src").path
        process.environment = env

        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr
        try process.run()
        process.waitUntilExit()

        let output = stdout.fileHandleForReading.readDataToEndOfFile()
        if process.terminationStatus != 0 {
            let errorData = stderr.fileHandleForReading.readDataToEndOfFile()
            let message = String(data: errorData, encoding: .utf8) ?? "unknown TLS material error"
            throw HarnessError.engineUnavailable(message)
        }
        return try JSONDecoder().decode(HarnessTLSMaterial.self, from: output)
    }

    // MARK: - Health

    private static func isHealthy(_ base: URL) async -> Bool {
        var req = URLRequest(url: base.appendingPathComponent("api/health"))
        req.timeoutInterval = 2
        do {
            let session = RemoteCertificatePinning.configuredSession()
            let (data, resp) = try await session.data(for: req)
            guard let http = resp as? HTTPURLResponse, http.statusCode == 200 else { return false }
            if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                return (obj["status"] as? String) == "healthy"
            }
            return true
        } catch {
            return false
        }
    }

    private static func waitForHealth(_ base: URL, timeout: TimeInterval) async -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if await isHealthy(base) { return true }
            try? await Task.sleep(nanoseconds: 500_000_000)
        }
        return false
    }

    /// Reads the engine's shared-secret token from its canonical on-disk path.
    /// Mirrors `_token_file_path()` in `fichero-engine/src/fichero/api/auth.py`:
    ///   `Path.home() / "Library" / "Application Support" / "Fichero" / ".api-key"`
    /// Uses `homeDirectoryForCurrentUser` because `url(for: .applicationSupportDirectory)`
    /// resolves to the sandbox container path in the XCTest host, not the real `~`.
    private static func readEngineToken() -> String? {
        let tokenURL = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Fichero/.api-key")
        guard let data = try? Data(contentsOf: tokenURL),
              let raw = String(data: data, encoding: .utf8) else { return nil }
        let token = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return token.isEmpty ? nil : token
    }

    // MARK: - Repo root

    /// FICHERO_REPO_ROOT if set, else walk up looking for a dir that contains both
    /// `.venv` and `fichero-engine`. Discovery is checkout-directory-name agnostic:
    /// it probes up from the loaded test bundle AND from this source file's
    /// compile-time path (`#filePath`), which always lives inside the repo, so the
    /// harness works regardless of what the checkout directory is named.
    static func repoRoot() -> URL? {
        let fileManager = FileManager.default
        if let env = ProcessInfo.processInfo.environment["FICHERO_REPO_ROOT"], !env.isEmpty {
            let url = URL(fileURLWithPath: env)
            if looksLikeRepo(url) { return url }
        }
        // `#filePath` = <repo>/fichero/fichero-tests/EngineHarness.swift, so walking up
        // from it reaches the repo even when the test bundle lives in DerivedData.
        for start in [Bundle(for: _HarnessAnchor.self).bundleURL,
                      URL(fileURLWithPath: #filePath)] {
            var dir = start
            for _ in 0..<12 {
                if looksLikeRepo(dir) { return dir }
                dir = dir.deletingLastPathComponent()
            }
        }
        // Last resort for local dev machines: the conventional checkout under ~/code/fichero.
        let fallback = fileManager.homeDirectoryForCurrentUser.appendingPathComponent("code/fichero")
        return looksLikeRepo(fallback) ? fallback : nil
    }

    private static func looksLikeRepo(_ url: URL) -> Bool {
        let fileManager = FileManager.default
        return fileManager.fileExists(atPath: url.appendingPathComponent(".venv/bin/python").path)
            && fileManager.fileExists(atPath: url.appendingPathComponent("fichero-engine/scripts/seed_test_library.py").path)
    }
}

/// Anchor for `Bundle(for:)` so we can locate the test bundle on disk.
private final class _HarnessAnchor {}
