// swiftlint:disable file_length
import FicheroAPIClient
import Foundation

/// Single source of truth for the Fichero engine base URL.
///
/// Every part of the app reads `EngineConfig.host` (engine root, e.g.
/// `http://127.0.0.1:8765`) or `EngineConfig.apiBaseURL` (the `/api` base)
/// instead of hardcoding `127.0.0.1:8765`. The host is user-configurable via
/// Settings -> Backend and falls back to localhost only when unset or blank.
/// Malformed non-empty values stay invalid instead of silently resolving to
/// localhost.
enum EngineConfig {
    static let userDefaultsKey = "fichero.engine.host"
    static let defaultHostString = "http://127.0.0.1:8765"
    static let engineHostDidChangeNotification = Notification.Name("engineHostDidChange")

    enum HostConfiguration: Equatable {
        case embeddedLocal
        case configured(URL)
        case invalid(String)

        var hostString: String {
            switch self {
            case .embeddedLocal:
                return EngineConfig.defaultHostString
            case let .configured(url):
                return url.absoluteString
            case let .invalid(raw):
                return raw
            }
        }

        var host: URL {
            switch self {
            case .embeddedLocal:
                return EngineConfig.makeDefaultHostURL()
            case let .configured(url):
                return url
            case let .invalid(raw):
                return EngineConfig.makeInvalidHostURL(raw)
            }
        }

        var usesCustomHost: Bool {
            if case .embeddedLocal = self {
                return false
            }
            return true
        }

        var engineIsLocal: Bool {
            switch self {
            case .embeddedLocal:
                return true
            case let .configured(url):
                return EngineConfig.isLocalHost(url)
            case .invalid:
                return false
            }
        }
    }

    static var hostString: String {
        resolvedHostConfiguration.hostString
    }

    /// Engine root — host + port, no `/api`, no trailing slash.
    /// (e.g. `http://127.0.0.1:8765`)
    static var host: URL {
        resolvedHostConfiguration.host
    }

    /// API base — the engine root with the `/api` prefix.
    /// (e.g. `http://127.0.0.1:8765/api`)
    static var apiBaseURL: URL {
        host.appendingPathComponent("api")
    }

    static var usesCustomHost: Bool {
        resolvedHostConfiguration.usesCustomHost
    }

    /// True when the configured engine host is localhost / 127.0.0.1 / ::1.
    /// Use this to guard "Reveal in Finder" and any other action that assumes
    /// the engine and the app share a local filesystem. When the engine is
    /// remote these actions must be hidden — local paths are meaningless.
    static var engineIsLocal: Bool {
        resolvedHostConfiguration.engineIsLocal
    }

    static func hostConfiguration(from raw: String?) -> HostConfiguration {
        guard let normalized = normalizedHostString(raw) else {
            return .embeddedLocal
        }
        guard let url = makeURL(normalized), url.host != nil else {
            return .invalid(normalized)
        }
        return .configured(url)
    }

    private static var resolvedHostConfiguration: HostConfiguration {
        hostConfiguration(from: UserDefaults.standard.string(forKey: userDefaultsKey))
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

    private static func isLocalHost(_ url: URL) -> Bool {
        guard let host = url.host?.lowercased() else { return false }
        return isLoopbackHostLiteral(host)
    }

    fileprivate static func isLoopbackHostLiteral(_ host: String) -> Bool {
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

        guard let mappedRange = normalized.range(of: "::ffff:") else {
            return false
        }
        let mappedIPv4 = String(normalized[mappedRange.upperBound...])
        return isIPv4LoopbackLiteral(mappedIPv4)
    }

    private static func makeDefaultHostURL() -> URL {
        guard let url = URL(string: defaultHostString) else {
            preconditionFailure("EngineConfig: malformed default URL literal '\(defaultHostString)'")
        }
        return url
    }

    private static func makeInvalidHostURL(_ raw: String) -> URL {
        var components = URLComponents()
        components.scheme = "invalid"
        components.host = "configured-engine"
        components.path = "/" + raw
        guard let url = components.url else {
            preconditionFailure("EngineConfig: unable to build invalid host sentinel for '\(raw)'")
        }
        return url
    }
}

enum RemoteAccessConfig {
    static let hostingEnabledKey = "fichero.remote_access.enabled"
    static let bonjourEnabledKey = "fichero.remote_access.bonjour_enabled"
    static let publicBaseURLKey = "fichero.remote_access.public_base_url"

    static var hostingEnabled: Bool {
        UserDefaults.standard.bool(forKey: hostingEnabledKey)
    }

    static var bonjourEnabled: Bool {
        UserDefaults.standard.bool(forKey: bonjourEnabledKey)
    }

    static var publicBaseURLString: String {
        let stored = UserDefaults.standard.string(forKey: publicBaseURLKey) ?? ""
        return stored.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static var publicBaseURL: URL? {
        try? validatedRemoteURL(from: publicBaseURLString, allowLocalhost: false)
    }

    static func pairingBackendURL(from publicBaseURLString: String) -> URL? {
        try? validatedRemoteURL(from: publicBaseURLString, allowLocalhost: false)
    }
}

enum RemoteURLValidationError: LocalizedError, Equatable {
    case blank
    case invalid
    case unsupportedScheme
    case missingHost
    case localhostNotAllowed
    case pathNotAllowed
    case queryNotAllowed
    case fragmentNotAllowed

    var errorDescription: String? {
        switch self {
        case .blank:
            return "Enter a reachable remote URL."
        case .invalid:
            return "Enter a valid remote URL."
        case .unsupportedScheme:
            return "Remote URLs must use http or https."
        case .missingHost:
            return "Remote URLs must include a host name."
        case .localhostNotAllowed:
            return "Remote clients must use a non-localhost host."
        case .pathNotAllowed:
            return "Remote URLs must be the backend root, without a path."
        case .queryNotAllowed:
            return "Remote URLs cannot include a query string."
        case .fragmentNotAllowed:
            return "Remote URLs cannot include a fragment."
        }
    }
}

func validatedRemoteURL(from raw: String, allowLocalhost: Bool) throws -> URL {
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else {
        throw RemoteURLValidationError.blank
    }

    guard var components = URLComponents(string: trimmed) else {
        throw RemoteURLValidationError.invalid
    }

    guard let scheme = components.scheme?.lowercased(), scheme == "http" || scheme == "https" else {
        throw RemoteURLValidationError.unsupportedScheme
    }
    guard let host = components.host, !host.isEmpty else {
        throw RemoteURLValidationError.missingHost
    }
    if !allowLocalhost, EngineConfig.isLoopbackHostLiteral(host.lowercased()) {
        throw RemoteURLValidationError.localhostNotAllowed
    }
    if !components.path.isEmpty, components.path != "/" {
        throw RemoteURLValidationError.pathNotAllowed
    }
    if components.query != nil {
        throw RemoteURLValidationError.queryNotAllowed
    }
    if components.fragment != nil {
        throw RemoteURLValidationError.fragmentNotAllowed
    }

    components.path = ""
    components.query = nil
    components.fragment = nil

    guard let url = components.url else {
        throw RemoteURLValidationError.invalid
    }
    return url
}

struct PairingQRCodePayload: Codable {
    let version: Int
    let apiURL: String
    let pairCode: String
    let expiresAt: Date
    let spki: String

    enum CodingKeys: String, CodingKey {
        case version = "v"
        case apiURL = "api_url"
        case pairCode = "pair_code"
        case expiresAt = "expires_at"
        case spki
    }
}

enum PairingQRCodePayloadDecoder {
    static func decode(message: String) throws -> PairingQRCodePayload {
        guard let payloadData = message.data(using: .utf8) else {
            throw APIError.badRequest("The QR code payload was not valid UTF-8.")
        }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let raw = try container.decode(String.self)
            guard let date = parseEngineDate(raw) else {
                throw DecodingError.dataCorruptedError(
                    in: container,
                    debugDescription: "Cannot decode QR payload date: \(raw)"
                )
            }
            return date
        }

        return try decoder.decode(PairingQRCodePayload.self, from: payloadData)
    }
}

struct PairingCodeRecord: Codable {
    let code: String
    let expiresAt: Date

    enum CodingKeys: String, CodingKey {
        case code
        case expiresAt = "expires_at"
    }
}

struct PairingExchangeRequest: Codable {
    let code: String
    let deviceName: String

    enum CodingKeys: String, CodingKey {
        case code
        case deviceName = "device_name"
    }
}

struct PairingExchangeResponse: Codable {
    let deviceId: String
    let deviceToken: String

    enum CodingKeys: String, CodingKey {
        case deviceId = "device_id"
        case deviceToken = "device_token"
    }
}

struct PairingExchangeResult: Equatable {
    let apiRoot: URL
    let deviceToken: String
}

struct PairedDeviceRecord: Codable, Identifiable {
    let id: String
    let name: String
    let userId: String
    let createdAt: Date
    let lastSeen: Date
    let expiresAt: Date
    let revoked: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case userId = "user_id"
        case createdAt = "created_at"
        case lastSeen = "last_seen"
        case expiresAt = "expires_at"
        case revoked
    }
}

private struct PairedDeviceListResponse: Codable {
    let items: [PairedDeviceRecord]
    let count: Int
}

private struct PairingStatusResponse: Codable {
    let status: String
}

@MainActor
final class PairingService {
    private let apiRoot: URL
    private let apiBaseURL: URL
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init(apiRoot: URL) {
        self.apiRoot = apiRoot
        self.apiBaseURL = apiRoot.appendingPathComponent("api")

        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 15
        configuration.timeoutIntervalForResource = 30
        self.session = URLSession(configuration: configuration)

        self.decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let raw = try container.decode(String.self)
            guard let date = parseEngineDate(raw) else {
                throw DecodingError.dataCorruptedError(
                    in: container,
                    debugDescription: "Cannot decode engine date: \(raw)"
                )
            }
            return date
        }

        self.encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
    }

    func createPairingCode() async throws -> PairingCodeRecord {
        var request = URLRequest(url: apiBaseURL.appendingPathComponent("pair/code"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        addAuthorization(to: &request)
        return try await decode(PairingCodeRecord.self, from: request)
    }

    func listDevices() async throws -> [PairedDeviceRecord] {
        var request = URLRequest(url: apiBaseURL.appendingPathComponent("pair/devices"))
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        addAuthorization(to: &request)
        let response = try await decode(PairedDeviceListResponse.self, from: request)
        return response.items
    }

    func revokeDevice(id: String) async throws {
        var request = URLRequest(url: apiBaseURL.appendingPathComponent("pair/devices/\(id)/revoke"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        addAuthorization(to: &request)
        _ = try await decode(PairingStatusResponse.self, from: request)
    }

    func pairDeviceUnauthenticated(code: String, deviceName: String) async throws -> PairingExchangeResponse {
        var request = URLRequest(url: apiBaseURL.appendingPathComponent("pair"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try encoder.encode(PairingExchangeRequest(code: code, deviceName: deviceName))
        // `/api/pair` is the remote-client bootstrap exchange. Never attach the
        // caller's current token here: a local/embedded `.api-key` must not be
        // forwarded to a different remote host.
        return try await decodeUnauthenticated(PairingExchangeResponse.self, from: request)
    }

    func buildQRCodePayload(from code: PairingCodeRecord, spki: String = "") -> PairingQRCodePayload {
        PairingQRCodePayload(
            version: 1,
            apiURL: apiRoot.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")),
            pairCode: code.code,
            expiresAt: code.expiresAt,
            spki: spki
        )
    }

    static func persistAuthToken(_ token: String, for apiRoot: URL) throws {
        try AuthTokenMiddleware.persistRemoteToken(token, hostString: apiRoot.absoluteString)
    }

    private func addAuthorization(to request: inout URLRequest) {
        if let token = AuthTokenMiddleware.readTokenFromDisk() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
    }

    private func decode<T: Decodable>(_ type: T.Type, from request: URLRequest) async throws -> T {
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(type, from: data)
    }

    private func decodeUnauthenticated<T: Decodable>(_ type: T.Type, from request: URLRequest) async throws -> T {
        var unauthenticatedRequest = request
        unauthenticatedRequest.setValue(nil, forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: unauthenticatedRequest)
        try validate(response: response, data: data)
        return try decoder.decode(type, from: data)
    }

    private func validate(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        guard (200...299).contains(http.statusCode) else {
            if let error = try? decoder.decode(ErrorResponse.self, from: data) {
                throw APIError.httpError(statusCode: http.statusCode, message: error.detail)
            }
            let message = String(data: data, encoding: .utf8) ?? "Unknown error"
            throw APIError.httpError(statusCode: http.statusCode, message: message)
        }
    }
}
