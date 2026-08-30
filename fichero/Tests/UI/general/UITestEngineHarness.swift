//
//  UITestEngineHarness.swift
//  FicheroUITests
//
//  Hermetic backend provisioning for XCUITests that must drive REAL data
//  through the app (#1230 follow-up: the data-dependent flows LibrarySmokeUITests
//  deferred — "select a document, open the inspector, entities load").
//
//  Unlike the in-process `EngineHarness` in Tests/Unit/general (which spins a TLS
//  uvicorn on :8765 for XCTest round-trips), a UI test drives the app as a
//  SEPARATE process, so the app — not the test — is the client.
//
//  Since the 2026-08-04 test-architecture decisions this type is a thin Swift
//  wrapper over the ONE shared spawn-per-run harness,
//  `fichero-server/scripts/test_engine_harness.py` — the same script the
//  pytest fixture (CLI/MCP legs) and the scripted UX smoke drive. It seeds the
//  synthetic --full library, spawns the UDS engine with parent-pid
//  accountability (#4400), waits bounded for /api/health, and prints one
//  ready-JSON line; this wrapper launches it, parses that line, and SIGTERMs
//  it in teardown (the script reaps the engine, unlinks the socket, and
//  removes its temp dir).
//
//  The app is pointed at that socket with `FICHERO_FORCE_UDS_PATH` (see
//  EngineConfig+Launch.swift). UDS sidesteps the cross-process TLS-pin dance
//  entirely — a UDS connection is trusted as owner, so no token/cert plumbing is
//  needed for the app to read the seeded library.
//
//  Everything is disposable and per-run: the socket, the library, and the app's
//  Application Support root (FICHERO_UITEST_HOME) all live under a unique temp
//  dir removed in teardown, so a run never touches the developer's real library
//  or a shared dev backend.
//

import Foundation

/// Spawns + tears down a disposable UDS engine over a freshly seeded library.
/// Foundation-only (the FicheroUITests target links no app code): pure Process
/// + FileManager, no FicheroAPIClient, no TLS.
final class UITestEngineHarness {
    struct SeededLibrary {
        /// Absolute path to the seeded `.fichero` library the app should open.
        let libraryPath: String
        /// AF_UNIX socket the engine binds and the app dials via FICHERO_FORCE_UDS_PATH.
        let socketPath: String
        /// Disposable Application Support root for the app (FICHERO_UITEST_HOME).
        let appHomePath: String
        /// Ground-truth counts the seeder read back (e.g. "entities", "claims").
        let expected: [String: Int]
        /// Seeded row ids by name (e.g. "doc_letter", "entity_person").
        let ids: [String: String]
    }

    enum HarnessError: Error, CustomStringConvertible {
        case repoRootNotFound
        case seedFailed(String)
        case engineDidNotBind(String)

        var description: String {
            switch self {
            case .repoRootNotFound:
                return "Could not locate the repo root (set FICHERO_REPO_ROOT)."
            case .seedFailed(let message):
                return "Seeding the UI-test library failed: \(message)"
            case .engineDidNotBind(let message):
                return "UDS engine never bound its socket: \(message)"
            }
        }
    }

    private var engineProcess: Process?
    private var tempDir: URL?

    /// Rolling tail of uvicorn's stderr, so a spawn failure names its cause
    /// ("ModuleNotFoundError", "address already in use") instead of just an
    /// exit status. A lock-guarded box rather than harness state because the
    /// readabilityHandler is `@Sendable` and runs on a background queue —
    /// capturing the (non-Sendable) harness there is a Swift 6 error.
    private final class StderrBuffer: @unchecked Sendable {
        private let lock = NSLock()
        private var tail = ""

        func append(_ chunk: String) {
            lock.lock()
            tail = String((tail + chunk).suffix(2000))
            lock.unlock()
        }

        var text: String {
            lock.lock()
            defer { lock.unlock() }
            return tail
        }
    }

    private let stderrBuffer = StderrBuffer()

    private var capturedStderr: String { stderrBuffer.text }

    // A global handle so an atexit hook guarantees no orphaned uvicorn survives
    // the test process (mirrors EngineHarness's backstop). Plain globals because
    // the C `atexit` callback cannot capture context.
    nonisolated(unsafe) private static var spawnedProcess: Process?
    nonisolated(unsafe) private static var atexitRegistered = false

    private static func terminateAtExit() {
        spawnedProcess?.terminate()
        spawnedProcess = nil
    }

    /// Launch the shared harness script and wait for its ready line.
    /// Throws on any failure so the test can `try` and fail cleanly.
    func start() throws -> SeededLibrary {
        guard let repo = Self.repoRoot() else { throw HarnessError.repoRootNotFound }
        guard let venvPython = Self.venvPython(for: repo) else {
            throw HarnessError.engineDidNotBind(
                "no venv python (tried repo/.venv, FICHERO_VENV, ~/code/fichero/.venv)")
        }

        // The SOCKET must fit the AF_UNIX sun_path limit AND live where the
        // sandboxed app can dial it (#4194), so the wrapper picks the path and
        // hands it to the script; everything else (library, app-home, temp
        // dir) is the script's to create and to destroy.
        let runID = UUID().uuidString
        let socketPath = Self.shortSocketPath(runID: runID)
        let script = repo.appendingPathComponent(
            "fichero-server/scripts/test_engine_harness.py")

        let (proc, out) = try launchHarnessScript(
            python: venvPython, script: script, repo: repo, socketPath: socketPath)
        engineProcess = proc
        Self.spawnedProcess = proc
        if !Self.atexitRegistered {
            // atexit needs a @convention(c) pointer: a non-capturing LITERAL
            // closure calling the static handler (a bare method reference
            // `Self.terminateAtExit` doesn't convert). Use the explicit type name
            // so no dynamic `Self` is captured.
            atexit { UITestEngineHarness.terminateAtExit() }
            Self.atexitRegistered = true
        }

        let ready = try readReadyLine(from: out, process: proc, timeout: 120)
        guard let library = ready["library"] as? String,
              let socket = ready["socket"] as? String,
              let appHome = ready["app_home"] as? String
        else {
            throw HarnessError.engineDidNotBind(
                "ready line missing library/socket/app_home: \(ready)")
        }
        let expected = (ready["expected"] as? [String: Int]) ?? [:]
        let keys = (ready["keys"] as? [String: String]) ?? [:]
        return SeededLibrary(
            libraryPath: library,
            socketPath: socket,
            appHomePath: appHome,
            expected: expected,
            ids: keys
        )
    }

    func stop() {
        // SIGTERM the script; its handler reaps the engine (#4400 backstops a
        // SIGKILLed runner), unlinks the socket, and removes its temp dir.
        engineProcess?.terminate()
        engineProcess = nil
        Self.spawnedProcess = nil
        if let tempDir { try? FileManager.default.removeItem(at: tempDir) }
        tempDir = nil
    }

    /// Spawn the harness script with its stderr tail captured for diagnostics.
    private func launchHarnessScript(
        python: URL, script: URL, repo: URL, socketPath: String
    ) throws -> (Process, Pipe) {
        let proc = Process()
        proc.executableURL = python
        proc.arguments = [script.path, "--socket", socketPath, "--seed-mode", "full"]
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = repo.appendingPathComponent("fichero-server/src").path
        proc.environment = env
        let out = Pipe()
        let errPipe = Pipe()
        proc.standardOutput = out
        proc.standardError = errPipe
        errPipe.fileHandleForReading.readabilityHandler = { [stderrBuffer] handle in
            let data = handle.availableData
            if data.isEmpty {
                handle.readabilityHandler = nil
            } else if let text = String(data: data, encoding: .utf8) {
                stderrBuffer.append(text)
            }
        }
        do {
            try proc.run()
        } catch {
            throw HarnessError.engineDidNotBind("could not launch harness script: \(error)")
        }
        return (proc, out)
    }

    // MARK: - Ready-line protocol

    /// The script's contract: first stdout line is one JSON object, printed
    /// only after /api/health answered over the socket. No line = FAILURE
    /// (loud, with the script's stderr), never a silent green.
    private func readReadyLine(
        from pipe: Pipe, process: Process, timeout: TimeInterval
    ) throws -> [String: Any] {
        let handle = pipe.fileHandleForReading
        var buffer = Data()
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            let chunk = handle.availableData
            if !chunk.isEmpty {
                buffer.append(chunk)
                if let newline = buffer.firstIndex(of: UInt8(ascii: "\n")) {
                    let line = buffer[..<newline]
                    guard let json = try? JSONSerialization
                        .jsonObject(with: Data(line)) as? [String: Any]
                    else {
                        throw HarnessError.engineDidNotBind(
                            "unparseable ready line: "
                            + (String(data: Data(line), encoding: .utf8) ?? "<binary>"))
                    }
                    return json
                }
            }
            if !process.isRunning {
                throw HarnessError.engineDidNotBind(
                    "harness script exited (status \(process.terminationStatus)) "
                    + "before ready; stderr: \(capturedStderr)")
            }
            Thread.sleep(forTimeInterval: 0.1)
        }
        throw HarnessError.engineDidNotBind(
            "no ready line within \(Int(timeout))s; stderr: \(capturedStderr)")
    }

    // MARK: - Paths

    /// A short socket path that fits the AF_UNIX `sun_path` limit. The deep
    /// per-run temp dir would overflow it, so the socket lives directly in
    /// NSTemporaryDirectory under a compact name derived from the run id.
    ///
    /// #4194 CAVEAT: this is the XCTRUNNER's temp dir. A SANDBOXED app under
    /// test gets `connect() errno 1 (Operation not permitted)` dialing it —
    /// the app logs that loudly while the test only sees "never ready" and
    /// polls. UDS harness suites are only valid against a non-sandboxed
    /// build (Dev schemes); the sandboxed MAS config needs a different
    /// transport or an app-group socket location.
    private static func shortSocketPath(runID: String) -> String {
        let shortID = String(runID.replacingOccurrences(of: "-", with: "").prefix(10))
        // The app under test is SANDBOXED — including Dev Local (verified on
        // the built product's entitlements, 2026-07-29). A sandboxed app can
        // only connect to an AF_UNIX socket inside its OWN container; the
        // runner's NSTemporaryDirectory is the RUNNER's container, which is
        // how every session suite failed with connect EPERM (#4194). Bind
        // where the dev run-loop already proved the app can reach: the app
        // container's tmp. Still under the sun_path ~104-byte limit (~88).
        let containerTmp = (realHome as NSString).appendingPathComponent(
            "Library/Containers/app.fichero.fichero/Data/tmp")
        try? FileManager.default.createDirectory(
            atPath: containerTmp, withIntermediateDirectories: true)
        return (containerTmp as NSString).appendingPathComponent("fut-\(shortID).sock")
    }

    // MARK: - Repo root

    /// FICHERO_REPO_ROOT if set, else walk up from this file (`#filePath` always
    /// lives inside the repo) looking for a dir with both `.venv/bin/python` and
    /// the seeder — checkout-directory-name agnostic, mirroring EngineHarness.
    static func repoRoot() -> URL? {
        if let env = ProcessInfo.processInfo.environment["FICHERO_REPO_ROOT"], !env.isEmpty {
            let url = URL(fileURLWithPath: env)
            if looksLikeRepo(url) { return url }
        }
        for start in [Bundle(for: UITestEngineHarness.self).bundleURL,
                      URL(fileURLWithPath: #filePath)] {
            var dir = start
            for _ in 0..<12 {
                if looksLikeRepo(dir) { return dir }
                dir = dir.deletingLastPathComponent()
            }
        }
        let fallback = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("code/fichero")
        return looksLikeRepo(fallback) ? fallback : nil
    }

    private static func looksLikeRepo(_ url: URL) -> Bool {
        // Only the engine SEEDER is required — a git worktree under test has the
        // engine but NOT its own `.venv` (that lives in the canonical checkout).
        // The venv is resolved separately by `venvPython(for:)`, so this no longer
        // demands both in the same dir (which made the harness skip in a worktree).
        FileManager.default.fileExists(
            atPath: url.appendingPathComponent("fichero-server/scripts/seed_test_library.py").path)
    }

    /// Real login home from the user database, ignoring any `$HOME` override. The
    /// Dev Local scheme overrides `$HOME` to the app container (dev parity) and the
    /// Test action inherits it (`shouldUseLaunchSchemeArgsEnv`), so
    /// `homeDirectoryForCurrentUser`/`NSHomeDirectory()` resolve the container —
    /// wrong for finding the canonical `~/code/fichero/.venv`.
    static var realHome: String { NSHomeDirectoryForUser(NSUserName()) ?? NSHomeDirectory() }

    /// The venv python used to run the engine. Prefers the repo's own `.venv`,
    /// else a `FICHERO_VENV` override, else the canonical `~/code/fichero/.venv`
    /// (a worktree under test has no venv of its own). nil if none exists.
    static func venvPython(for repo: URL) -> URL? {
        let fileManager = FileManager.default
        var candidates = [repo.appendingPathComponent(".venv/bin/python")]
        if let override = ProcessInfo.processInfo.environment["FICHERO_VENV"], !override.isEmpty {
            candidates.append(URL(fileURLWithPath: override).appendingPathComponent("bin/python"))
        }
        // Derive the canonical checkout from THIS file's real path (`#filePath`),
        // which the test process can read (repoRoot already resolved via it) and
        // which ignores the container-polluted `$HOME`. Worktrees live under
        // `<root>/code/fichero-worktrees/*`; the canonical checkout with the venv
        // is `<root>/code/fichero`.
        if let code = codeAncestor(of: URL(fileURLWithPath: #filePath)) {
            candidates.append(code.appendingPathComponent("fichero/.venv/bin/python"))
        }
        candidates.append(URL(fileURLWithPath: realHome)
            .appendingPathComponent("code/fichero/.venv/bin/python"))
        return candidates.first { fileManager.fileExists(atPath: $0.path) }
    }

    /// The `code` directory ancestor of `url` (e.g. `/Users/x/code`), or nil.
    private static func codeAncestor(of url: URL) -> URL? {
        var cursor = url
        while cursor.pathComponents.count > 1 {
            if cursor.lastPathComponent == "code" { return cursor }
            cursor = cursor.deletingLastPathComponent()
        }
        return nil
    }
}
