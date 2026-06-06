import Foundation

/// Single source of truth for the Fichero engine base URL.
///
/// Every part of the app reads `EngineConfig.host` (engine root, e.g.
/// `http://127.0.0.1:8765`) or `EngineConfig.apiBaseURL` (the `/api` base)
/// instead of hardcoding `127.0.0.1:8765`. Changing the engine location is a
/// one-line edit here. This also unblocks a future configurable engine URL.
enum EngineConfig {
    /// Engine root — host + port, no `/api`, no trailing slash.
    /// (e.g. `http://127.0.0.1:8765`)
    static let host = makeURL("http://127.0.0.1:8765")

    /// API base — the engine root with the `/api` prefix.
    /// (e.g. `http://127.0.0.1:8765/api`)
    static let apiBaseURL = host.appendingPathComponent("api")

    /// Build a URL from a known-good compile-time constant, trapping with a
    /// clear message if the literal is ever malformed. Used only for the
    /// static strings above — never for user/dynamic data.
    private static func makeURL(_ string: String) -> URL {
        guard let url = URL(string: string) else {
            preconditionFailure("EngineConfig: malformed URL literal '\(string)'")
        }
        return url
    }
}
