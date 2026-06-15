import Foundation
import HTTPTypes
import OpenAPIRuntime

/// Middleware that adds `Authorization: Bearer <token>` to every request,
/// reading the token from `~/Library/Application Support/Fichero/.api-key`.
///
/// The engine writes that file (mode 0600) at startup. See
/// `fichero-engine/src/fichero/api/auth.py` (#742). Skipping the header on
/// `/api/health` lets the Swift app poll readiness *before* it has had a
/// chance to read the token, which avoids a chicken-and-egg deadlock at
/// app launch.
///
/// **Token is read fresh on every request** (not cached at init), because
/// FicheroClient is constructed at app startup, before the engine has had
/// time to write the file. Caching would freeze `token = nil` and every
/// authenticated call would 401 forever. Disk read is ~43 bytes; cost is
/// negligible compared to the network round-trip.
public struct AuthTokenMiddleware: ClientMiddleware {
    /// Endpoints the engine accepts unauthenticated. Keep in sync with
    /// `_UNAUTHENTICATED_PATHS` in the Python side.
    private static let unauthenticatedPaths: [String] = [
        "/api/health",
        "/openapi.json",
        "/docs",
        "/redoc"
    ]

    public init() {}

    // Backward-compat shim: older call sites pass a token but it's ignored
    // (we always read fresh from disk).
    public init(token: String?) {}

    public static func isUnauthenticatedPath(_ path: String) -> Bool {
        unauthenticatedPaths.contains { path.contains($0) }
    }

    public static func tokenFileURL() -> URL? {
        guard
            let appSupport = try? FileManager.default.url(
                for: .applicationSupportDirectory,
                in: .userDomainMask,
                appropriateFor: nil,
                create: false
            )
        else {
            return nil
        }
        return appSupport
            .appendingPathComponent("Fichero")
            .appendingPathComponent(".api-key")
    }

    /// Reads the token file from disk. Returns nil if the file isn't there
    /// yet (e.g., engine hasn't started). Callers should retry; the engine
    /// writes this on startup before binding the port.
    ///
    /// **Env override:** if `FICHERO_AUTH_TOKEN` is set, its value is returned
    /// directly without touching the file. This lets the XCTest harness inject
    /// the engine's real token when the sandbox redirects
    /// `applicationSupportDirectory` to a container path different from where
    /// the engine wrote the file. See `EngineHarness.live()`.
    public static func readTokenFromDisk() -> String? {
        // Env override — used by the test harness to bridge the sandbox gap.
        if let envToken = ProcessInfo.processInfo.environment["FICHERO_AUTH_TOKEN"] {
            let trimmed = envToken.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty { return trimmed }
        }
        guard let path = tokenFileURL() else { return nil }
        guard let data = try? Data(contentsOf: path) else { return nil }
        guard let rawToken = String(data: data, encoding: .utf8) else { return nil }
        let token = rawToken
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return token.isEmpty ? nil : token
    }

    public static func waitForToken(timeout: TimeInterval = 3) async -> String? {
        if let token = readTokenFromDisk() { return token }
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            try? await Task.sleep(for: .milliseconds(50))
            if let token = readTokenFromDisk() { return token }
        }
        return nil
    }

    public static func waitForTokenBlocking(timeout: TimeInterval = 3) -> String? {
        if let token = readTokenFromDisk() { return token }
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            Thread.sleep(forTimeInterval: 0.05)
            if let token = readTokenFromDisk() { return token }
        }
        return nil
    }

    public func intercept(
        _ request: HTTPRequest,
        body: HTTPBody?,
        baseURL: URL,
        operationID: String,
        next: (HTTPRequest, HTTPBody?, URL) async throws -> (HTTPResponse, HTTPBody?)
    ) async throws -> (HTTPResponse, HTTPBody?) {
        var request = request
        let path = request.path ?? ""
        let isUnauthenticated = Self.isUnauthenticatedPath(path)

        // Read the token fresh on every request — see class doc for why.
        if !isUnauthenticated, let token = await Self.waitForToken() {
            request.headerFields[.authorization] = "Bearer \(token)"
        }

        return try await next(request, body, baseURL)
    }
}
