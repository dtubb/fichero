//
//  UITestEngineHarness.swift
//  FicheroUITests
//
//  Hermetic backend provisioning for XCUITests that must drive REAL data
//  through the app (#1230 follow-up: the data-dependent flows LibrarySmokeUITests
//  deferred — "select a document, open the inspector, entities load").
//
//  Unlike the in-process `EngineHarness` in fichero-tests (which spins a TLS
//  uvicorn on :8765 for XCTest round-trips), a UI test drives the app as a
//  SEPARATE process, so the app — not the test — is the client. This harness
//  therefore:
//    1. Seeds a disposable `.fichero` library with the SAME Python seeder the
//       contract walker uses (entities + claims included), then
//    2. Spawns the engine on a Unix-domain socket (no TCP, no TLS) — the exact
//       `fichero.api.uds_transport:app --uds …` fast-loop start_backend.sh uses.
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

    /// Seed a library, spawn the UDS engine, and wait for the socket to bind.
    /// Throws on any failure so the test can `try` and skip cleanly.
    func start() throws -> SeededLibrary {
        guard let repo = Self.repoRoot() else { throw HarnessError.repoRootNotFound }

        // The library + app-home live under a unique temp dir (path length is
        // irrelevant here). The SOCKET, however, must fit the AF_UNIX sun_path
        // limit (~104 bytes), so it goes straight in NSTemporaryDirectory under a
        // short name instead of the deep per-run dir.
        let runID = UUID().uuidString
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("fichero-uitest-\(runID)", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        tempDir = dir

        let libURL = dir.appendingPathComponent("Seed.fichero", isDirectory: true)
        let appHome = dir.appendingPathComponent("AppHome", isDirectory: true)
        try FileManager.default.createDirectory(at: appHome, withIntermediateDirectories: true)

        let socketPath = Self.shortSocketPath(runID: runID)

        let (expected, ids) = try seedLibrary(at: libURL, repo: repo)
        try spawnEngine(repo: repo, socketPath: socketPath, appHome: appHome)
        try waitForSocket(socketPath, timeout: 90)

        return SeededLibrary(
            libraryPath: libURL.path,
            socketPath: socketPath,
            appHomePath: appHome.path,
            expected: expected,
            ids: ids
        )
    }

    func stop() {
        engineProcess?.terminate()
        engineProcess = nil
        Self.spawnedProcess = nil
        if let tempDir { try? FileManager.default.removeItem(at: tempDir) }
        tempDir = nil
    }

    // MARK: - Seeding

    private func seedLibrary(at libURL: URL, repo: URL) throws -> ([String: Int], [String: String]) {
        guard let venvPython = Self.venvPython(for: repo) else {
            throw HarnessError.seedFailed("no venv python (tried repo/.venv, FICHERO_VENV, ~/code/fichero/.venv)")
        }
        let seeder = repo.appendingPathComponent("fichero-engine/scripts/seed_test_library.py")

        let proc = Process()
        proc.executableURL = venvPython
        proc.arguments = [seeder.path, libURL.path]
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = repo.appendingPathComponent("fichero-engine/src").path
        proc.environment = env
        let out = Pipe()
        let err = Pipe()
        proc.standardOutput = out
        proc.standardError = err
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
            let errText = String(data: err.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            throw HarnessError.seedFailed(
                "exit \(proc.terminationStatus); out=\(String(data: data, encoding: .utf8) ?? "<none>"); err=\(errText)"
            )
        }
        return (expected, keys)
    }

    // MARK: - Spawn (UDS, no TCP, no TLS)

    private func spawnEngine(repo: URL, socketPath: String, appHome: URL) throws {
        // Stale socket from a crashed prior run would make bind fail.
        try? FileManager.default.removeItem(atPath: socketPath)

        guard let venvPython = Self.venvPython(for: repo) else {
            throw HarnessError.engineDidNotBind("no venv python (tried repo/.venv, FICHERO_VENV, ~/code/fichero/.venv)")
        }
        let proc = Process()
        proc.executableURL = venvPython
        // Mirrors start_backend.sh's UDS fast loop exactly.
        proc.arguments = [
            "-m", "uvicorn",
            "fichero.api.uds_transport:app",
            "--uds", socketPath,
            "--ws", "websockets-sansio"
        ]
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = repo.appendingPathComponent("fichero-engine/src").path
        env["FICHERO_UDS_PATH"] = socketPath
        // Owner-trusted UDS, single-user, dev tier (beta-gated KG routes exposed),
        // auth disabled so the app needs no token over the socket.
        env["FICHERO_MULTIUSER"] = "0"
        env["FICHERO_FEATURE_TIER"] = "dev"
        env["FICHERO_DISABLE_AUTH"] = "1"
        // Keep the engine's own state off the developer's real Application Support:
        // point HOME at the disposable app-home so any engine-side dotfiles land there.
        env["HOME"] = appHome.path
        // The engine watches this PID and self-terminates if the test process dies
        // before atexit runs (SIGKILL / crash) — the robust orphan backstop.
        env["FICHERO_PARENT_PID"] = String(ProcessInfo.processInfo.processIdentifier)
        proc.environment = env
        proc.standardOutput = Pipe()
        let errPipe = Pipe()
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
            throw HarnessError.engineDidNotBind("could not launch uvicorn: \(error)")
        }
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
    }

    /// Wait until the engine binds its socket. The engine's cold import is ~2s;
    /// this polls for the socket FILE and then confirms it accepts a connection,
    /// so the app's first request over UDS won't race the bind.
    private func waitForSocket(_ path: String, timeout: TimeInterval) throws {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if FileManager.default.fileExists(atPath: path), Self.canConnect(to: path) {
                return
            }
            if let proc = engineProcess, !proc.isRunning {
                throw HarnessError.engineDidNotBind(
                    "uvicorn exited early (status \(proc.terminationStatus)); stderr: \(capturedStderr)"
                )
            }
            Thread.sleep(forTimeInterval: 0.25)
        }
        throw HarnessError.engineDidNotBind(
            "socket \(path) never accepted a connection within \(Int(timeout))s; stderr: \(capturedStderr)"
        )
    }

    /// Best-effort AF_UNIX connect probe — true once uvicorn is accepting.
    private static func canConnect(to path: String) -> Bool {
        let fd = socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else { return false }
        defer { close(fd) }
        var addr = sockaddr_un()
        addr.sun_family = sa_family_t(AF_UNIX)
        let maxLen = MemoryLayout.size(ofValue: addr.sun_path)
        var ok = false
        path.withCString { cstr in
            if strlen(cstr) < maxLen {
                _ = withUnsafeMutablePointer(to: &addr.sun_path) { dst in
                    dst.withMemoryRebound(to: CChar.self, capacity: maxLen) { dstPtr in
                        strcpy(dstPtr, cstr)
                    }
                }
                let size = socklen_t(MemoryLayout<sockaddr_un>.size)
                ok = withUnsafePointer(to: &addr) { ptr in
                    ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sa in
                        connect(fd, sa, size) == 0
                    }
                }
            }
        }
        return ok
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
        let path = (NSTemporaryDirectory() as NSString)
            .appendingPathComponent("fut-\(shortID).sock")
        return path
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
            atPath: url.appendingPathComponent("fichero-engine/scripts/seed_test_library.py").path)
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
        let fm = FileManager.default
        var candidates = [repo.appendingPathComponent(".venv/bin/python")]
        if let v = ProcessInfo.processInfo.environment["FICHERO_VENV"], !v.isEmpty {
            candidates.append(URL(fileURLWithPath: v).appendingPathComponent("bin/python"))
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
        return candidates.first { fm.fileExists(atPath: $0.path) }
    }

    /// The `code` directory ancestor of `url` (e.g. `/Users/x/code`), or nil.
    private static func codeAncestor(of url: URL) -> URL? {
        var u = url
        while u.pathComponents.count > 1 {
            if u.lastPathComponent == "code" { return u }
            u = u.deletingLastPathComponent()
        }
        return nil
    }
}
