import Foundation
import HTTPTypes
import OpenAPIRuntime
import Security

// swiftlint:disable type_body_length file_length
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

    /// True when `hostString` (or the global default) is a loopback engine, so
    /// requests to it authenticate with the bootstrap `.api-key` rather than a
    /// remote device/session token. Public so callers building a per-library
    /// backend host can derive its token kind (#2866).
    public static func prefersLocalhostEngineToken(hostString: String? = nil) -> Bool {
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
        readTokenFromDisk(hostString: nil)
    }

    /// Host-aware token read (#2866). The app can hold multiple backends at once
    /// (local embedded engine + N remote hosts), so the token is resolved per
    /// REQUEST HOST, not off the single global default: a loopback host reads
    /// the bootstrap `.api-key`; a remote host reads that host's device token
    /// from the Keychain. Pass `nil` for the global default (the legacy path).
    public static func readTokenFromDisk(hostString: String?) -> String? {
        let kind = tokenStorageKind(hostString: hostString)
        // Env override — test-harness bridge for the LOCAL engine only. A remote
        // host must never borrow the local test token.
        if kind == .bootstrap,
           let envToken = ProcessInfo.processInfo.environment["FICHERO_AUTH_TOKEN"] {
            let trimmed = envToken.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty { return trimmed }
        }
        switch kind {
        case .bootstrap:
            guard let path = bootstrapTokenFileURL() else { return nil }
            guard let data = try? Data(contentsOf: path) else { return nil }
            guard let rawToken = String(data: data, encoding: .utf8) else { return nil }
            let token = rawToken
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return token.isEmpty ? nil : token
        case .remote:
            return readRemoteTokenFromKeychain(hostString: hostString)
        }
    }

    /// The device token's protection class (#3772).
    ///
    /// EXPLICIT, not inherited. Before this, no `kSecAttrAccessible` was set anywhere
    /// in this file, so the item took the platform default — which is unreadable
    /// before first unlock, and is an unstated default we would be trusting with a
    /// security-critical item.
    ///
    /// `AfterFirstUnlock`, not `WhenUnlocked`: the app must be able to read the token
    /// on a launch that happens before the user unlocks. NOT a `ThisDeviceOnly`
    /// variant: those cannot sync, which would foreclose the zero-touch work later.
    static let remoteTokenAccessibility = kSecAttrAccessibleAfterFirstUnlock

    public static func persistRemoteToken(_ token: String, hostString: String) throws {
        let trimmed = token.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let data = trimmed.data(using: .utf8) else { return }

        let query = remoteTokenKeychainQuery(hostString: hostString)
        // The UPDATE path must carry the accessibility too — otherwise the first
        // re-pair after this fix would silently write the old, attribute-less item
        // back and the bug would return.
        let attributes: [String: Any] = [
            kSecValueData as String: data,
            kSecAttrAccessible as String: remoteTokenAccessibility
        ]
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
            addQuery[kSecAttrAccessible as String] = remoteTokenAccessibility
            let addStatus = SecItemAdd(addQuery as CFDictionary, nil)
            guard addStatus == errSecSuccess else {
                throw AuthTokenStorageError.keychainWriteFailed(addStatus)
            }
        default:
            throw AuthTokenStorageError.keychainReadFailed(status)
        }
    }

    /// The protection class the token is ACTUALLY stored with, read back out of the
    /// Keychain — not what we believe we passed (#3772). nil when no token is stored.
    ///
    /// Public because the fix is only real if it can be asserted from the test target,
    /// and because the restore diagnostic reports it.
    public static func remoteTokenAccessibilityValue(hostString: String? = nil) -> String? {
        var query = remoteTokenKeychainQuery(hostString: hostString)
        query[kSecReturnAttributes as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let attributes = result as? [String: Any] else {
            return nil
        }
        return attributes[kSecAttrAccessible as String] as? String
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
            kSecAttrAccount as String: remoteTokenKeychainAccount(hostString: hostString),
            // Apple recommends this unconditionally. It is on EVERY query — read,
            // write, and clear — because a query without it addresses a DIFFERENT
            // keychain on macOS, and a mismatched pair would write where it cannot
            // read. (Consequence, deliberate: a macOS token written before this
            // change lives in the legacy keychain and will not be found, so that Mac
            // re-pairs once. iOS is unaffected — it has only the data-protection
            // keychain.)
            kSecUseDataProtectionKeychain as String: true
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
        await waitForToken(hostString: nil, timeout: timeout)
    }

    /// Host-aware token wait (#2866) — resolves the token for a specific backend
    /// host, so a request bound for one engine never waits on / uses another's.
    public static func waitForToken(hostString: String?, timeout: TimeInterval = 3) async -> String? {
        if let token = readTokenFromDisk(hostString: hostString) { return token }
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            try? await Task.sleep(for: .milliseconds(50))
            if let token = readTokenFromDisk(hostString: hostString) { return token }
        }
        return nil
    }

    public static func waitForTokenBlocking(timeout: TimeInterval = 3) -> String? {
        waitForTokenBlocking(hostString: nil, timeout: timeout)
    }

    /// Host-aware blocking token wait (#2866) — for the raw-URLSession auth path
    /// (`URLRequest.addEngineAuth`) which resolves the token for the request's host.
    public static func waitForTokenBlocking(hostString: String?, timeout: TimeInterval = 3) -> String? {
        if let token = readTokenFromDisk(hostString: hostString) { return token }
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            Thread.sleep(forTimeInterval: 0.05)
            if let token = readTokenFromDisk(hostString: hostString) { return token }
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
        // Token is resolved off THIS request's baseURL, not the global host
        // (#2866): the app can hold multiple backends (local + N remote) at
        // once, and each carries its own bootstrap/device/session credential.
        // A local embedded engine must use its current bootstrap secret. A stale
        // Keychain session otherwise overrides the fresh sandbox token after an
        // engine restart and traps the app in a 401 reset loop (#3852). Remote
        // hosts retain session-first multi-user authentication.
        if !isUnauthenticated {
            let host = baseURL.absoluteString
            let isLoopback = Self.prefersLocalhostEngineToken(hostString: host)
            if isLoopback, let token = await Self.waitForToken(hostString: host) {
                request.headerFields[.authorization] = "Bearer \(token)"
            } else if !isLoopback, let session = Self.readSessionToken(hostString: host) {
                request.headerFields[.authorization] = "Bearer \(session)"
            } else if let token = await Self.waitForToken(hostString: host) {
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
