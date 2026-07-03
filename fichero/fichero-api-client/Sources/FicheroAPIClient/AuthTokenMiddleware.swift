import Foundation
import HTTPTypes
import OpenAPIRuntime
import Security

// swiftlint:disable type_body_length
/// Middleware that adds `Authorization: Bearer <token>` to every request,
/// reading the token from `~/Library/Application Support/Fichero/.api-key`.
///
/// The engine writes that file (mode 0600) at startup. See
/// `fichero-engine/src/fichero/api/auth.py` (#742). Skipping the header on
/// `/api/health` lets the Swift app poll readiness *before* it has had a
/// chance to read the token, which avoids a chicken-and-egg deadlock at
/// app launch. `/api/pair` is also skipped so the unauthenticated pairing
/// exchange never forwards a local bootstrap token to a remote host.
///
/// **Token is read fresh on every request** (not cached at init), because
/// FicheroClient is constructed at app startup, before the engine has had
/// time to write the file. Caching would freeze `token = nil` and every
/// authenticated call would 401 forever. Disk read is ~43 bytes; cost is
/// negligible compared to the network round-trip.
public struct AuthTokenMiddleware: ClientMiddleware {
    private static let engineHostUserDefaultsKey = "fichero.engine.host"
    private static let defaultHostString = "https://127.0.0.1:8765"
    private static let bootstrapTokenFileName = ".api-key"
    private static let remoteTokenFilePrefix = ".remote-api-key-"
    private static let remoteTokenKeychainService = "app.fichero.fichero.remote-device-token"
    /// Keychain service for the multi-user *session* token minted by
    /// `POST /api/auth/login`. Distinct from the bootstrap/device tokens: this
    /// carries the logged-in user's identity + per-library role, which the
    /// bootstrap `.api-key` (owner-for-admin, but `request.state.user == nil`)
    /// does not, so a library only loads under multi-user once a session exists.
    private static let sessionTokenKeychainService = "app.fichero.fichero.session-token"

    /// Endpoints the engine accepts unauthenticated. Keep in sync with
    /// `_UNAUTHENTICATED_PATHS` in the Python side.
    private static let unauthenticatedPaths: [String] = [
        "/api/health",
        "/api/auth/login",
        "/api/pair",
        "/openapi.json",
        "/docs",
        "/redoc"
    ]

    public init() {}

    // Backward-compat shim: older call sites pass a token but it's ignored
    // (we always read fresh from disk).
    public init(token: String?) {}

    public static func isUnauthenticatedPath(_ path: String) -> Bool {
        unauthenticatedPaths.contains { allowedPath in
            if path == allowedPath { return true }
            // `/api/pair` is an exact unauthenticated exchange path; sub-paths
            // such as `/api/pair/code` and `/api/pair/devices` require auth.
            if allowedPath == "/api/pair" { return false }
            return path.hasPrefix("\(allowedPath)/")
        }
    }

    enum TokenStorageKind: Equatable {
        case bootstrap
        case remote
    }

    static func tokenStorageKind(hostString: String? = nil) -> TokenStorageKind {
        prefersLocalhostEngineToken(hostString: hostString) ? .bootstrap : .remote
    }

    static func applicationSupportDirectoryURL() -> URL? {
        try? FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
    }

    public static func bootstrapTokenFileURL() -> URL? {
        if let hostURL = hostHomeTokenFileURL() {
            return hostURL
        }
        guard let appSupport = applicationSupportDirectoryURL() else { return nil }
        return appSupport
            .appendingPathComponent("Fichero")
            .appendingPathComponent(bootstrapTokenFileName)
    }

    public static func remoteTokenFileURL(hostString: String? = nil) -> URL? {
        guard let appSupport = applicationSupportDirectoryURL() else { return nil }
        return appSupport
            .appendingPathComponent("Fichero")
            .appendingPathComponent(remoteTokenFileName(hostString: hostString))
    }

    public static func tokenFileURL() -> URL? {
        switch tokenStorageKind() {
        case .bootstrap:
            return bootstrapTokenFileURL()
        case .remote:
            return remoteTokenFileURL()
        }
    }

    private static func hostHomeTokenFileURL() -> URL? {
        #if targetEnvironment(simulator) && !os(macOS)
        guard prefersLocalhostEngineToken() else { return nil }
        if let hostHome = ProcessInfo.processInfo.environment["SIMULATOR_HOST_HOME"],
           !hostHome.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return URL(fileURLWithPath: hostHome)
                .appendingPathComponent("Library/Application Support/Fichero/\(bootstrapTokenFileName)")
        }
        return nil
        #else
        return nil
        #endif
    }

    static func prefersLocalhostEngineToken(hostString: String? = nil) -> Bool {
        guard let stored = hostString ?? UserDefaults.standard.string(forKey: engineHostUserDefaultsKey) else {
            return true
        }
        let trimmed = stored.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return true }
        guard let host = URL(string: trimmed)?.host?.lowercased() else {
            return false
        }
        return isLoopbackHostLiteral(host)
    }

    private static func isLoopbackHostLiteral(_ host: String) -> Bool {
        if host == "localhost" {
            return true
        }

        let trimmedHost = host.trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
        if isIPv4LoopbackLiteral(trimmedHost) {
            return true
        }
        return isIPv6LoopbackLiteral(trimmedHost)
    }

    private static func isIPv4LoopbackLiteral(_ host: String) -> Bool {
        let octets = host.split(separator: ".", omittingEmptySubsequences: false)
        guard octets.count == 4 else { return false }
        let numbers = octets.compactMap { Int($0) }
        guard numbers.count == 4, numbers.allSatisfy({ (0...255).contains($0) }) else { return false }
        return numbers[0] == 127
    }

    private static func isIPv6LoopbackLiteral(_ host: String) -> Bool {
        let normalized = host.lowercased()
        if normalized == "::1" || normalized == "0:0:0:0:0:0:0:1" {
            return true
        }

        let mappedPrefix = "::ffff:"
        guard normalized.hasPrefix(mappedPrefix) else {
            return false
        }
        let mappedIPv4 = String(normalized.dropFirst(mappedPrefix.count))
        return isIPv4LoopbackLiteral(mappedIPv4)
    }

    static func remoteTokenFileName(hostString: String? = nil) -> String {
        let stored = hostString ?? UserDefaults.standard.string(forKey: engineHostUserDefaultsKey)
        let trimmed = (stored ?? defaultHostString)
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        let normalized = trimmed.replacingOccurrences(
            of: "[^a-z0-9]+",
            with: "-",
            options: .regularExpression
        )
        let suffix = normalized.trimmingCharacters(in: CharacterSet(charactersIn: "-"))
        let identifier = suffix.isEmpty ? "default" : suffix
        return "\(remoteTokenFilePrefix)\(identifier)"
    }

    static func remoteTokenKeychainAccount(hostString: String? = nil) -> String {
        "remote-device-token|\(normalizedRemoteHostString(hostString: hostString))"
    }

    public static func normalizedRemoteHostString(hostString: String? = nil) -> String {
        let stored = hostString ?? UserDefaults.standard.string(forKey: engineHostUserDefaultsKey)
        let trimmed = (stored ?? defaultHostString).trimmingCharacters(in: .whitespacesAndNewlines)

        guard var components = URLComponents(string: trimmed) else {
            return trimmed
        }

        components.scheme = components.scheme?.lowercased()
        components.host = components.host?.lowercased()
        if let scheme = components.scheme?.lowercased(),
           let port = components.port,
           (scheme == "https" && port == 443) || (scheme == "http" && port == 80) {
            components.port = nil
        }
        components.path = ""
        components.query = nil
        components.fragment = nil

        return components.string ?? trimmed
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
        switch tokenStorageKind() {
        case .bootstrap:
            guard let path = tokenFileURL() else { return nil }
            guard let data = try? Data(contentsOf: path) else { return nil }
            guard let rawToken = String(data: data, encoding: .utf8) else { return nil }
            let token = rawToken
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return token.isEmpty ? nil : token
        case .remote:
            return readRemoteTokenFromKeychain()
        }
    }

    public static func persistRemoteToken(_ token: String, hostString: String) throws {
        let trimmed = token.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let data = trimmed.data(using: .utf8) else { return }

        let query = remoteTokenKeychainQuery(hostString: hostString)
        let attributes: [String: Any] = [kSecValueData as String: data]
        let status = SecItemCopyMatching(query as CFDictionary, nil)

        switch status {
        case errSecSuccess:
            let updateStatus = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
            guard updateStatus == errSecSuccess else {
                throw AuthTokenStorageError.keychainWriteFailed(updateStatus)
            }
        case errSecItemNotFound:
            var addQuery = query
            addQuery[kSecValueData as String] = data
            let addStatus = SecItemAdd(addQuery as CFDictionary, nil)
            guard addStatus == errSecSuccess else {
                throw AuthTokenStorageError.keychainWriteFailed(addStatus)
            }
        default:
            throw AuthTokenStorageError.keychainReadFailed(status)
        }
    }

    public static func readRemoteTokenForHost(_ hostString: String) -> String? {
        readRemoteTokenFromKeychain(hostString: hostString)
    }

    public static func clearRemoteToken(hostString: String) {
        let query = remoteTokenKeychainQuery(hostString: hostString)
        SecItemDelete(query as CFDictionary)
        removeLegacyRemoteTokenFile(hostString: hostString)
    }

    private static func removeLegacyRemoteTokenFile(hostString: String) {
        guard let legacyURL = remoteTokenFileURL(hostString: hostString) else {
            return
        }
        try? FileManager.default.removeItem(at: legacyURL)
    }

    private static func readRemoteTokenFromKeychain(hostString: String? = nil) -> String? {
        var query = remoteTokenKeychainQuery(hostString: hostString)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess,
              let data = result as? Data,
              let rawToken = String(data: data, encoding: .utf8) else {
            return nil
        }

        let token = rawToken.trimmingCharacters(in: .whitespacesAndNewlines)
        return token.isEmpty ? nil : token
    }

    private static func remoteTokenKeychainQuery(hostString: String? = nil) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: remoteTokenKeychainService,
            kSecAttrAccount as String: remoteTokenKeychainAccount(hostString: hostString)
        ]
    }

    // MARK: - Session token (multi-user login, #2021/#2022)

    /// Per-host Keychain account for the login session token. Host-scoped like
    /// the remote device token so a session for one engine can never be
    /// attached to a request bound for a different host.
    public static func sessionTokenKeychainAccount(hostString: String? = nil) -> String {
        "session-token|\(normalizedRemoteHostString(hostString: hostString))"
    }

    private static func sessionTokenKeychainQuery(hostString: String? = nil) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: sessionTokenKeychainService,
            kSecAttrAccount as String: sessionTokenKeychainAccount(hostString: hostString)
        ]
    }

    /// Store the session token returned by `POST /api/auth/login`. Secrets live
    /// in the Keychain, never UserDefaults. Never logged by callers.
    public static func persistSessionToken(_ token: String, hostString: String? = nil) throws {
        let trimmed = token.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let data = trimmed.data(using: .utf8) else { return }

        let query = sessionTokenKeychainQuery(hostString: hostString)
        let attributes: [String: Any] = [kSecValueData as String: data]
        let status = SecItemCopyMatching(query as CFDictionary, nil)

        switch status {
        case errSecSuccess:
            let updateStatus = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
            guard updateStatus == errSecSuccess else {
                throw AuthTokenStorageError.keychainWriteFailed(updateStatus)
            }
        case errSecItemNotFound:
            var addQuery = query
            addQuery[kSecValueData as String] = data
            let addStatus = SecItemAdd(addQuery as CFDictionary, nil)
            guard addStatus == errSecSuccess else {
                throw AuthTokenStorageError.keychainWriteFailed(addStatus)
            }
        default:
            throw AuthTokenStorageError.keychainReadFailed(status)
        }
    }

    public static func readSessionToken(hostString: String? = nil) -> String? {
        var query = sessionTokenKeychainQuery(hostString: hostString)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess,
              let data = result as? Data,
              let rawToken = String(data: data, encoding: .utf8) else {
            return nil
        }

        let token = rawToken.trimmingCharacters(in: .whitespacesAndNewlines)
        return token.isEmpty ? nil : token
    }

    public static func clearSessionToken(hostString: String? = nil) {
        SecItemDelete(sessionTokenKeychainQuery(hostString: hostString) as CFDictionary)
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
        // A login *session* token (multi-user) takes priority over the
        // bootstrap/device token: once a user is signed in, their session
        // carries the identity + per-library role the library load needs. When
        // no session exists yet (pre-login, first-owner bootstrap) we fall back
        // to the bootstrap/device token so /api/users and create-owner still work.
        if !isUnauthenticated {
            if let session = Self.readSessionToken() {
                request.headerFields[.authorization] = "Bearer \(session)"
            } else if let token = await Self.waitForToken() {
                request.headerFields[.authorization] = "Bearer \(token)"
            }
        }

        return try await next(request, body, baseURL)
    }
}
// swiftlint:enable type_body_length

enum AuthTokenStorageError: Error, Equatable {
    case keychainReadFailed(OSStatus)
    case keychainWriteFailed(OSStatus)
}
