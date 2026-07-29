#if os(macOS)
import Foundation

/// Loads the Fichero engine's FastAPI ASGI app for the in-process (`.inMemory`)
/// transport, booting CPython exactly once and caching the resulting handle.
///
/// The underlying `PythonWorker`/`ASGIAppLoader` read libpython + `sys.path`
/// entries from the environment (`PYTHON_LIBRARY`, `PYTHONHOME`,
/// `FICHERO_ENGINE_SRC`, `FICHERO_VENV_SITE_PACKAGES`) and fail LOUD if the
/// engine module can't be imported. This helper only supplies *dev defaults* for
/// the two Fichero-specific `sys.path` entries when they're unset, so a plain
/// `⌘R` Debug build can drive the checked-out engine without extra scheme env.
/// Anything already exported in the environment wins (env-overridable).
enum InMemoryEngineApp {
    /// Dotted module path of the engine's ASGI application object.
    private static let engineModule = "fichero_server.api.main"
    /// Module-level attribute holding the FastAPI instance (`app = FastAPI(...)`).
    private static let engineAttribute = "app"

    /// Dev-default source tree + venv site-packages. Overridden by the matching
    /// environment variables when present; only applied if the path exists so a
    /// stale default never shadows a real env value silently.
    ///
    /// Derived from `$HOME` rather than hardcoded: these were absolute paths
    /// under one developer's home directory, so the in-memory engine could only
    /// ever load on that one machine — silently falling back to "no app" for
    /// everyone else, since the guard below only applies a default that exists.
    /// A checkout elsewhere sets `FICHERO_ENGINE_SRC` / `FICHERO_VENV_ROOT`.
    private static let defaultEngineSrc =
        NSHomeDirectory() + "/code/fichero/fichero-server/src"
    private static let defaultVenvRoot =
        NSHomeDirectory() + "/code/fichero/.venv"

    private static let lock = NSLock()
    private static var cached: ASGIApp?

    /// The engine ASGI app handle, loaded once. Blocks on first call while the
    /// interpreter boots and the FastAPI app (+ its C extensions) import.
    static func shared() -> ASGIApp {
        lock.lock()
        defer { lock.unlock() }
        if let cached { return cached }
        applyDevDefaultsIfUnset()
        let app = ASGIAppLoader.importApp(module: engineModule, attribute: engineAttribute)
        cached = app
        return app
    }

    // MARK: - Environment

    private static func applyDevDefaultsIfUnset() {
        setDefaultIfUnset("FICHERO_ENGINE_SRC", defaultEngineSrc)
        if let sitePackages = discoveredSitePackages() {
            setDefaultIfUnset("FICHERO_VENV_SITE_PACKAGES", sitePackages)
        }
    }

    /// Export `value` as `key` only when the env var is absent/empty and the path
    /// exists on disk. `overwrite: 0` in `setenv` keeps any real env value.
    private static func setDefaultIfUnset(_ key: String, _ value: String) {
        let existing = ProcessInfo.processInfo.environment[key]
        guard existing == nil || existing?.isEmpty == true else { return }
        guard FileManager.default.fileExists(atPath: value) else {
            FileHandle.standardError.write(
                Data("InMemoryEngineApp: default \(key)=\(value) does not exist; leaving unset\n".utf8)
            )
            return
        }
        setenv(key, value, 0)
    }

    /// Resolve `<venvRoot>/lib/python3.*/site-packages`, tolerant of the exact
    /// CPython minor version (the venv is `python3.12` today but shouldn't be
    /// pinned here). Prefers an explicit `FICHERO_VENV_SITE_PACKAGES` if set.
    private static func discoveredSitePackages() -> String? {
        if let explicit = ProcessInfo.processInfo.environment["FICHERO_VENV_SITE_PACKAGES"],
           !explicit.isEmpty {
            return explicit
        }
        let libDir = "\(defaultVenvRoot)/lib"
        guard let entries = try? FileManager.default.contentsOfDirectory(atPath: libDir) else {
            return nil
        }
        for name in entries.sorted() where name.hasPrefix("python3") {
            let candidate = "\(libDir)/\(name)/site-packages"
            if FileManager.default.fileExists(atPath: candidate) { return candidate }
        }
        return nil
    }
}
#endif
