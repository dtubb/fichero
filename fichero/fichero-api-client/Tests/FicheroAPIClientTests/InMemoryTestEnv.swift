#if os(macOS)
import Foundation
import XCTest

/// Shared environment discovery + skip gate for the in-process (`.inMemory`)
/// engine tests. The in-memory transport boots CPython via PythonKit and
/// imports the real Fichero engine `app` in-process — no subprocess, no
/// socket, no HTTP server. These helpers locate the repo checkout, derive
/// the env vars the embedded interpreter needs, export any that are unset, and
/// `XCTSkip` the test when the toolchain or engine can't be found so a box
/// without the embedded engine stays green.
///
/// Reused by `InMemoryTransportSmokeTests`, the streaming/cancellation/
/// concurrency harness, and the transport-agnostic routing matrix
/// (`TransportRoutingMatrixTests`) — one env gate for every in-process test.
enum InMemoryTestEnv {

    /// Locate the repo, derive the embedded-interpreter env, export any unset
    /// vars, and throw `XCTSkip` if the toolchain/engine isn't discoverable.
    /// Call from `setUp` (or per-test) before touching `InMemoryEngineApp`.
    static func configureOrSkip() throws {
        guard let repo = repoRoot() else {
            throw XCTSkip("No Fichero checkout with .venv + fichero-server found; "
                + "in-process engine unavailable.")
        }
        let fileManager = FileManager.default

        // FICHERO_ENGINE_SRC
        let engineSrc = repo.appendingPathComponent("fichero-server/src")
        guard fileManager.fileExists(atPath: engineSrc.appendingPathComponent("fichero_server/api/main.py").path) else {
            throw XCTSkip("Engine source not found at \(engineSrc.path); cannot import fichero_server.api.main.")
        }
        setenvIfUnset("FICHERO_ENGINE_SRC", engineSrc.path)

        // FICHERO_VENV_SITE_PACKAGES (tolerant of the exact python3.* minor)
        guard let sitePackages = discoverSitePackages(venvRoot: repo.appendingPathComponent(".venv")) else {
            throw XCTSkip("No .venv site-packages under \(repo.path)/.venv; engine deps unavailable.")
        }
        setenvIfUnset("FICHERO_VENV_SITE_PACKAGES", sitePackages)

        // PYTHON_LIBRARY (ask the venv python for the definitive framework binary).
        guard let libpython = discoverLibpython(venvRoot: repo.appendingPathComponent(".venv")) else {
            throw XCTSkip("Could not resolve libpython from the venv; PythonKit cannot boot CPython.")
        }
        setenvIfUnset("PYTHON_LIBRARY", libpython)
    }

    static func setenvIfUnset(_ key: String, _ value: String) {
        if let existing = ProcessInfo.processInfo.environment[key], !existing.isEmpty { return }
        setenv(key, value, 0)
    }

    static func discoverSitePackages(venvRoot: URL) -> String? {
        let libDir = venvRoot.appendingPathComponent("lib")
        guard let entries = try? FileManager.default.contentsOfDirectory(atPath: libDir.path) else { return nil }
        for name in entries.sorted() where name.hasPrefix("python3") {
            let candidate = libDir.appendingPathComponent(name).appendingPathComponent("site-packages")
            if FileManager.default.fileExists(atPath: candidate.path) { return candidate.path }
        }
        return nil
    }

    /// Run the venv's own python to resolve the CPython framework binary path —
    /// machine-agnostic (works for any Homebrew/pyenv/framework layout).
    static func discoverLibpython(venvRoot: URL) -> String? {
        let python = venvRoot.appendingPathComponent("bin/python")
        guard FileManager.default.fileExists(atPath: python.path) else { return nil }
        let process = Process()
        process.executableURL = python
        process.arguments = ["-c",
            "import sysconfig,os;"
            + "p=sysconfig.get_config_var('PYTHONFRAMEWORKPREFIX');"
            + "fw=sysconfig.get_config_var('PYTHONFRAMEWORK');"
            + "v=sysconfig.get_config_var('py_version_short');"
            + "print(os.path.join(p, fw+'.framework','Versions',v,fw) if p and fw else '')"
        ]
        let out = Pipe()
        process.standardOutput = out
        process.standardError = Pipe()
        guard (try? process.run()) != nil else { return nil }
        process.waitUntilExit()
        let data = out.fileHandleForReading.readDataToEndOfFile()
        let path = String(decoding: data, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
        return (!path.isEmpty && FileManager.default.fileExists(atPath: path)) ? path : nil
    }

    /// Walk up from this source file (always inside the repo) looking for a dir
    /// that contains both `.venv/bin/python` and `fichero-server`. Honors
    /// `FICHERO_REPO_ROOT` when set.
    static func repoRoot() -> URL? {
        let fileManager = FileManager.default
        func looksLikeRepo(_ url: URL) -> Bool {
            fileManager.fileExists(atPath: url.appendingPathComponent(".venv/bin/python").path)
                && fileManager.fileExists(atPath: url.appendingPathComponent("fichero-server/src").path)
        }
        if let env = ProcessInfo.processInfo.environment["FICHERO_REPO_ROOT"], !env.isEmpty {
            let url = URL(fileURLWithPath: env)
            if looksLikeRepo(url) { return url }
        }
        var dir = URL(fileURLWithPath: #filePath)
        for _ in 0..<12 {
            if looksLikeRepo(dir) { return dir }
            dir = dir.deletingLastPathComponent()
        }
        // Last resort: the conventional local checkout.
        let fallback = fileManager.homeDirectoryForCurrentUser.appendingPathComponent("code/fichero")
        return looksLikeRepo(fallback) ? fallback : nil
    }

    /// Gate for tests that touch the app DB (authenticated endpoints, the
    /// change stream). The engine's `StorageSettings.base_path` — and thus
    /// `app.duckdb` — is frozen at `storage` module IMPORT time from
    /// `FICHERO_BASE_PATH` (Pydantic settings, env_prefix `FICHERO_`). Setting
    /// it at test time is too late once the engine is imported. So the caller
    /// MUST export `FICHERO_BASE_PATH` to an isolated dir before the test
    /// process starts (the run script does this). Skip when it's unset so the
    /// suite stays green on boxes that haven't — the public-health tests still
    /// run, since they don't touch the app DB.
    static func requireIsolatedBasePath() throws {
        let value = ProcessInfo.processInfo.environment["FICHERO_BASE_PATH"] ?? ""
        guard !value.isEmpty else {
            throw XCTSkip("Set FICHERO_BASE_PATH to an isolated dir before running the "
                + "authenticated/streaming in-process tests (avoids the running "
                + "engine's app.duckdb lock + clobbering real engine state).")
        }
    }

    /// A throwaway per-test HOME whose `.api-key` the in-process engine reads
    /// (Python `Path.home()` honors $HOME, and the token is read fresh per
    /// request — not cached at import). Used to give the engine a known
    /// bootstrap token without clobbering the developer's real `.api-key`.
    /// Pair with `requireIsolatedBasePath()` so `app.duckdb` is isolated too.
    /// Returns a `restore` closure the caller MUST `defer { restore() }` so the
    /// `$HOME` override never leaks to other tests in the process.
    static func isolatedHomeWithBootstrapToken() throws -> (home: URL, token: String, restore: () -> Void) {
        let token = "inmemory-test-\(UUID().uuidString)"
        let home = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("inmem-home-\(UUID().uuidString)")
        try FileManager.default.createDirectory(atPath: home.path, withIntermediateDirectories: true)
        let support = home.appendingPathComponent("Library/Application Support/Fichero")
        try FileManager.default.createDirectory(atPath: support.path, withIntermediateDirectories: true)
        let keyFile = support.appendingPathComponent(".api-key")
        try token.write(to: keyFile, atomically: true, encoding: .utf8)
        // Mirror the engine's 0600 mode so a paranoid read doesn't reject it.
        try? FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: keyFile.path)

        let priorHome = ProcessInfo.processInfo.environment["HOME"] ?? ""
        setenv("HOME", home.path, 1)
        let restore: () -> Void = {
            setenv("HOME", priorHome, 1)
            try? FileManager.default.removeItem(at: home)
        }
        return (home, token, restore)
    }
}
#endif