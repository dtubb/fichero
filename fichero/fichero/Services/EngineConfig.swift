import Foundation

/// Single source of truth for the Fichero engine base URL.
///
/// Every part of the app reads `EngineConfig.host` (engine root, e.g.
/// `http://127.0.0.1:8765`) or `EngineConfig.apiBaseURL` (the `/api` base)
/// instead of hardcoding `127.0.0.1:8765`. The host is user-configurable via
/// Settings -> Backend and falls back to localhost when unset or malformed.
enum EngineConfig {
    static let userDefaultsKey = "fichero.engine.host"
    static let defaultHostString = "http://127.0.0.1:8765"

    static var hostString: String {
        let stored = UserDefaults.standard.string(forKey: userDefaultsKey)
        let normalized = normalizedHostString(stored) ?? defaultHostString
        return makeURL(normalized) == nil ? defaultHostString : normalized
    }

    /// Engine root — host + port, no `/api`, no trailing slash.
    /// (e.g. `http://127.0.0.1:8765`)
    static var host: URL {
        guard let url = makeURL(hostString) else {
            return makeDefaultHostURL()
        }
        return url
    }

    /// API base — the engine root with the `/api` prefix.
    /// (e.g. `http://127.0.0.1:8765/api`)
    static var apiBaseURL: URL {
        host.appendingPathComponent("api")
    }

    static var usesCustomHost: Bool {
        hostString != defaultHostString
    }

    /// True when the configured engine host is localhost / 127.0.0.1 / ::1.
    /// Use this to guard "Reveal in Finder" and any other action that assumes
    /// the engine and the app share a local filesystem. When the engine is
    /// remote these actions must be hidden — local paths are meaningless.
    static var engineIsLocal: Bool {
        guard let host = URL(string: hostString)?.host else { return true }
        return host == "localhost" || host == "127.0.0.1" || host == "::1"
    }

    private static func normalizedHostString(_ raw: String?) -> String? {
        guard let raw else { return nil }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        return trimmed.replacingOccurrences(of: "/+$", with: "", options: .regularExpression)
    }

    private static func makeURL(_ string: String) -> URL? {
        URL(string: string)
    }

    private static func makeDefaultHostURL() -> URL {
        guard let url = URL(string: defaultHostString) else {
            preconditionFailure("EngineConfig: malformed default URL literal '\(defaultHostString)'")
        }
        return url
    }
}
