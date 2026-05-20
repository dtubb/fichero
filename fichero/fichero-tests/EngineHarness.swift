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

    private static let baseURL = URL(string: "http://127.0.0.1:8765")!

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
        let proc = Process()
        proc.executableURL = uvicorn
        proc.arguments = ["fichero.api.main:app", "--port", "8765"]
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = repo.appendingPathComponent("fichero-engine/src").path
        env["FICHERO_DISABLE_AUTH"] = "1"
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

    // MARK: - Health

    private static func isHealthy(_ base: URL) async -> Bool {
        var req = URLRequest(url: base.appendingPathComponent("api/health"))
        req.timeoutInterval = 2
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
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

    // MARK: - Repo root

    /// FICHERO_REPO_ROOT if set, else walk up from the test bundle looking for
    /// a dir that contains both `.venv` and `fichero-engine`.
    static func repoRoot() -> URL? {
        let fileManager = FileManager.default
        if let env = ProcessInfo.processInfo.environment["FICHERO_REPO_ROOT"], !env.isEmpty {
            let url = URL(fileURLWithPath: env)
            if looksLikeRepo(url) { return url }
        }
        var dir = Bundle(for: _HarnessAnchor.self).bundleURL
        for _ in 0..<12 {
            if looksLikeRepo(dir) { return dir }
            // The repo is `fichero-0.0.2/` and the Xcode project lives in
            // `fichero-0.0.2/fichero/`, so also probe the parent each step.
            let inner = dir.appendingPathComponent("fichero-0.0.2")
            if looksLikeRepo(inner) { return inner }
            dir = dir.deletingLastPathComponent()
        }
        // Last resort for local dev machines.
        let fallback = fileManager.homeDirectoryForCurrentUser.appendingPathComponent("code/fichero-0.0.2")
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
