// swiftlint:disable file_length
import Darwin
import FicheroAPIClient
import Foundation
#if canImport(AppKit)
import AppKit
#endif

// EngineConfig is the app's config hub; its body exceeds the default limit.
// swiftlint:disable type_body_length
/// Single source of truth for the Fichero engine base URL.
///
/// Every part of the app reads `EngineConfig.host` (engine root, e.g.
/// `https://127.0.0.1:8765`) or `EngineConfig.apiBaseURL` (the `/api` base)
/// instead of hardcoding `127.0.0.1:8765`. The host is user-configurable via
/// Settings -> Backend. Only the macOS embedded-engine path implicitly
/// resolves a blank host to localhost; mobile clients require an explicit
/// remote host instead. Malformed non-empty values stay invalid instead of
/// silently resolving to localhost.
enum EngineConfig {
    static let userDefaultsKey = "fichero.engine.host"
    static let multiuserEnabledKey = "fichero.multiuser.enabled"
    static let defaultHostString = "https://127.0.0.1:8765"
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

        var requiresExternalBackendConnection: Bool {
            switch self {
            case .embeddedLocal:
                return false
            case .configured, .invalid:
                return true
            }
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
    /// (e.g. `https://127.0.0.1:8765`)
    static var host: URL {
        #if os(macOS)
        // macOS runs the engine locally. Keep the host app on loopback;
        // publicBaseURL is only for QR/invite payloads consumed by others (#2604).
        return resolvedHostConfiguration.host
        #else
        // iOS/iPadOS never runs a local engine. Connect straight to the
        // saved/paired remote host as the first candidate — never probe
        // localhost, which has no engine and only times out before the real
        // (remote) host is tried (#2465). Falls back to the resolved sentinel
        // when nothing is paired yet, preserving the setup-screen behaviour.
        return connectionCandidates.first ?? resolvedHostConfiguration.host
        #endif
    }

    // MARK: - Connection candidate ordering

    /// Engine hosts to attempt, in priority order, when establishing the
    /// initial connection. The first reachable candidate wins.
    ///
    /// Branches by platform because only macOS runs a local engine:
    /// - **macOS** tries the local engine (`defaultHostString`) first and a
    ///   configured non-loopback remote host (if any) as the fallback.
    /// - **iOS / iPadOS** has no local engine, so the saved/paired remote host
    ///   is the first (and only) candidate. localhost is omitted entirely —
    ///   probing it just times out and delays connecting to the real engine
    ///   (#2465).
    static var connectionCandidates: [URL] {
        orderedConnectionCandidates(
            savedHostString: UserDefaults.standard.string(forKey: userDefaultsKey),
            isMacOS: allowsEmbeddedLocalDefault
        )
    }

    /// Pure, dependency-injected ordering used by `connectionCandidates`.
    /// `savedHostString` is the persisted `fichero.engine.host`; `isMacOS`
    /// selects the platform branch. Exposed (rather than inlined) so the
    /// ordering can be unit-tested without mutating `UserDefaults` or the
    /// build platform.
    static func orderedConnectionCandidates(
        savedHostString: String?,
        isMacOS: Bool
    ) -> [URL] {
        let savedRemote: URL?
        if case let .configured(url) = hostConfiguration(
            from: savedHostString,
            allowsImplicitEmbeddedLocalDefault: false
        ) {
            savedRemote = url
        } else {
            savedRemote = nil
        }

        guard isMacOS else {
            // iOS: saved/paired remote first, localhost never.
            return savedRemote.map { [$0] } ?? []
        }

        // macOS: local engine first, configured non-loopback remote fallback.
        var candidates = [makeDefaultHostURL()]
        if let savedRemote,
           let savedHost = savedRemote.host?.lowercased(),
           !isLoopbackHostLiteral(savedHost) {
            candidates.append(savedRemote)
        }
        return candidates
    }

    /// API base — the engine root with the `/api` prefix.
    /// (e.g. `https://127.0.0.1:8765/api`)
    static var apiBaseURL: URL {
        host.appendingPathComponent("api")
    }

    static var usesCustomHost: Bool {
        resolvedHostConfiguration.usesCustomHost
    }

    static var hasConfiguredHost: Bool {
        if case .configured = resolvedHostConfiguration {
            return true
        }
        return false
    }

    /// True when startup should connect to an explicit configured backend
    /// instead of launching or restarting the embedded engine.
    static var requiresExternalBackendConnection: Bool {
        resolvedHostConfiguration.requiresExternalBackendConnection
    }

    static var multiuserEnabled: Bool {
        let defaults = UserDefaults.standard
        guard defaults.object(forKey: multiuserEnabledKey) != nil else {
            // Default OFF: multi-user is a shared/multi-person feature and the frontend
            // has no login flow yet (#2022 auth is cli-only). Defaulting ON spawns the
            // backend with FICHERO_MULTIUSER=1, whose fail-closed ACL choke-point then
            // 401/403s the app's own requests so no library loads.
            return false
        }
        return defaults.bool(forKey: multiuserEnabledKey)
    }

    /// True when the configured engine host is localhost / 127.0.0.1 / ::1.
    /// Use this to guard "Reveal in Finder" and any other action that assumes
    /// the engine and the app share a local filesystem. When the engine is
    /// remote these actions must be hidden — local paths are meaningless.
    static var engineIsLocal: Bool {
        resolvedHostConfiguration.engineIsLocal
    }

    // MARK: - Mac launch connection mode (#2381)

    /// How a macOS launch should establish its engine connection.
    ///
    /// A normal launch uses the embedded local engine — backend URL/debug
    /// fields stay out of regular Settings. Holding Option at launch instead
    /// exposes the explicit remote-client connection flow (scan/paste a host
    /// pairing link) for connecting this Mac to another Fichero host.
    enum MacLaunchConnectionMode: Equatable {
        /// Start the embedded local engine (the default for a normal launch).
        case embeddedLocal
        /// Present the remote-client connection chooser (Option held at launch).
        case remoteConnectionChooser
    }

    /// Pure launch-mode decision, dependency-injected so it can be unit-tested
    /// without AppKit or a real launch.
    ///
    /// - `optionKeyHeld`: was Option down as the app launched.
    /// - `isInteractiveLaunch`: false for Xcode Previews / Playgrounds / UI-test
    ///   / XCTest hosts, which drive the app non-interactively and must never
    ///   pop the chooser. The chooser only appears for a deliberate Option-held
    ///   interactive launch.
    static func macLaunchConnectionMode(
        optionKeyHeld: Bool,
        isInteractiveLaunch: Bool
    ) -> MacLaunchConnectionMode {
        guard isInteractiveLaunch, optionKeyHeld else {
            return .embeddedLocal
        }
        return .remoteConnectionChooser
    }

    #if os(macOS)
    /// True when Option is currently held — a snapshot of AppKit's modifier
    /// flags read once at launch. Isolated here so `macLaunchConnectionMode`
    /// above stays a pure, AppKit-free, unit-testable decision.
    static func optionKeyHeldAtLaunch() -> Bool {
        NSEvent.modifierFlags.contains(.option)
    }
    #endif

    // MARK: - Engine provisioning strategy (#3109)

    /// How a launch obtains its engine — decided ONCE from explicit inputs
    /// instead of re-derived from scattered `#if DEBUG` / `usesCustomHost` /
    /// preview conditionals. `EmbeddedBackendService.start()` and both app
    /// entries consume this rather than each re-deciding (#2861/#3042).
    ///
    /// The future iOS in-process embed (#2865) slots in here as one more case;
    /// the seam is deliberate — do NOT implement it yet.
    enum EngineProvisioningStrategy: Equatable {
        /// Previews / XCTest host / UI-test: adopt an external engine if one is
        /// already up, else run inert. NEVER spawn or manage a lifecycle.
        case inert
        /// An explicit configured host (Settings), macOS or iOS: connect to it,
        /// never spawn a local engine.
        case configuredRemote
        /// iOS paired companion (or first-run setup): a remote host, no local
        /// engine ever (#2465 — never probe localhost).
        case iosCompanion
        /// macOS Debug: adopt a developer-run engine on :8765. The engine is
        /// deliberately NOT bundled in Debug (#3042), so this never spawns — if
        /// nothing is up it fails with the actionable start_backend.sh message.
        case debugExternal
        /// macOS Release: spawn the bundled engine, app-authoritative token
        /// (#2862). The only strategy that spawns and manages a lifecycle.
        case releaseEmbedded

        /// True only for the one strategy that spawns the bundled engine
        /// subprocess. Debug/remote/inert all adopt an engine they didn't spawn.
        var spawnsBundledEngine: Bool { self == .releaseEmbedded }

        /// True when startup connects to an explicit/remote host instead of a
        /// local engine — the old `requiresExternalBackendConnection` branch the
        /// app entries used.
        var connectsToRemoteHost: Bool {
            self == .configuredRemote || self == .iosCompanion
        }
    }

    /// Pure, dependency-injected provisioning decision so every input
    /// combination is unit-testable without a real launch, AppKit, or a build
    /// flag. Precedence: inert host → explicit configured host → platform
    /// default (iOS companion; macOS Debug-external / Release-embedded).
    static func engineProvisioningStrategy(
        _ inputs: EngineProvisioningInputs
    ) -> EngineProvisioningStrategy {
        if inputs.isInertHost { return .inert }
        guard inputs.isMacOS else {
            // iOS never runs a local engine. A valid Settings host →
            // configuredRemote; otherwise the paired companion / first-run setup.
            return inputs.hasExplicitConfiguredHost ? .configuredRemote : .iosCompanion
        }
        // macOS: a configured (or malformed) remote host wins over the local
        // engine, matching `requiresExternalBackendConnection`.
        if inputs.hostRequiresRemoteConnection { return .configuredRemote }
        return inputs.isDebugBuild ? .debugExternal : .releaseEmbedded
    }

    /// The explicit inputs the provisioning decision reads. Captured as a value
    /// so tests can enumerate every combination.
    struct EngineProvisioningInputs: Equatable {
        /// This platform runs a local engine (macOS true, iOS false).
        let isMacOS: Bool
        /// Compiled for Debug (the engine isn't bundled, #3042).
        let isDebugBuild: Bool
        /// Preview / XCTest host / UI-test — drive the app non-interactively.
        let isInertHost: Bool
        /// A configured OR malformed host is set (`requiresExternalBackendConnection`).
        let hostRequiresRemoteConnection: Bool
        /// A VALID `.configured` host is set (`hasConfiguredHost`) — distinguishes
        /// an iOS Settings host (configuredRemote) from a paired companion.
        let hasExplicitConfiguredHost: Bool
    }

    /// The live provisioning strategy — reads the real platform, build config,
    /// launch environment, and saved host. Impure boundary around the pure
    /// `engineProvisioningStrategy(_:)`, mirroring `optionKeyHeldAtLaunch`.
    static func engineProvisioningStrategy() -> EngineProvisioningStrategy {
        engineProvisioningStrategy(currentEngineProvisioningInputs())
    }

    static func currentEngineProvisioningInputs() -> EngineProvisioningInputs {
        let env = ProcessInfo.processInfo.environment
        let isPreview = env["XCODE_RUNNING_FOR_PREVIEWS"] == "1"
            || env["XCODE_RUNNING_FOR_PLAYGROUNDS"] == "1"
        return EngineProvisioningInputs(
            isMacOS: allowsEmbeddedLocalDefault,
            isDebugBuild: isDebugBuild,
            isInertHost: isPreview || isRunningXCTests() || isUITesting(),
            hostRequiresRemoteConnection: requiresExternalBackendConnection,
            hasExplicitConfiguredHost: hasConfiguredHost
        )
    }

    private static var isDebugBuild: Bool {
        #if DEBUG
        return true
        #else
        return false
        #endif
    }

    static func hostConfiguration(from raw: String?) -> HostConfiguration {
        hostConfiguration(
            from: raw,
            allowsImplicitEmbeddedLocalDefault: allowsEmbeddedLocalDefault
        )
    }

    static func hostConfiguration(
        from raw: String?,
        allowsImplicitEmbeddedLocalDefault: Bool
    ) -> HostConfiguration {
        guard let normalized = normalizedHostString(raw) else {
            return allowsImplicitEmbeddedLocalDefault ? .embeddedLocal : .invalid("")
        }
        guard let url = makeURL(normalized), url.host != nil else {
            return .invalid(normalized)
        }
        guard url.scheme?.lowercased() == "https" else {
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

    private static var allowsEmbeddedLocalDefault: Bool {
        #if os(macOS)
        true
        #else
        false
        #endif
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
// swiftlint:enable type_body_length

/// Describes WHERE a library's engine lives so the sidebar can show a small
/// local-vs-remote badge on each library row (#2574). "Front-end-first":
/// today every open library shares the app-level `EngineConfig` host, so the
/// descriptor is derived from it via ``current()``. Once a per-library
/// `host` lands on `LibraryReference`, only that one call site changes — the
/// badge UI keeps reading `library.locationDescriptor`.
struct LibraryLocationDescriptor: Equatable {
    /// True when the engine runs on the same machine as the app.
    let isLocal: Bool
    /// Short human label, e.g. "On this Mac" or "On studio.local".
    let label: String
    /// SF Symbol for the badge.
    let systemImage: String

    /// Derives the descriptor from the app-level `EngineConfig` host.
    static func current() -> LibraryLocationDescriptor {
        if EngineConfig.engineIsLocal {
            #if os(macOS)
            return LibraryLocationDescriptor(
                isLocal: true,
                label: "On this Mac",
                systemImage: "laptopcomputer"
            )
            #else
            return LibraryLocationDescriptor(
                isLocal: true,
                label: "On this device",
                systemImage: "ipad"
            )
            #endif
        }
        let hostName = EngineConfig.host.host ?? EngineConfig.hostString
        return LibraryLocationDescriptor(
            isLocal: false,
            label: "On \(hostName)",
            systemImage: "network"
        )
    }
}

enum RemoteAccessConfig {
    static let hostingEnabledKey = "fichero.remote_access.enabled"
    static let bonjourEnabledKey = "fichero.remote_access.bonjour_enabled"
    static let publicBaseURLKey = "fichero.remote_access.public_base_url"
    static let pairedLibraryPathKey = "fichero.remote_access.paired_library_path"

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
        try? validatedHostedRemoteURL(from: publicBaseURLString)
    }

    static var advertisedSPKIPin: String {
        RemoteCertificatePinning.advertisedSPKIPin(hostString: publicBaseURLString) ?? ""
    }

    static var pairedLibraryPath: String {
        (UserDefaults.standard.string(forKey: pairedLibraryPathKey) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static var hasPairedLibraryPath: Bool {
        !pairedLibraryPath.isEmpty
    }

    static func pairingBackendURL(from publicBaseURLString: String) -> URL? {
        try? validatedRemoteURL(from: publicBaseURLString, allowLocalhost: false, requireSecureTransportForRemote: true)
    }

    static func launchEnvironment(
        for publicBaseURL: URL,
        material: RemoteAccessTLSMaterial,
        bonjourEnabled: Bool
    ) -> [String: String] {
        var environment = [
            "FICHERO_MULTIUSER": EngineConfig.multiuserEnabled ? "1" : "0",
            "FICHERO_ALLOW_NON_LOOPBACK_BIND": "I_UNDERSTAND_SHARED_SECRET_RISK",
            "FICHERO_BIND_HOST": material.bindHost,
            "FICHERO_PUBLIC_BASE_URL": publicBaseURL.absoluteString,
            "FICHERO_TLS_CERTFILE": material.certificatePath,
            "FICHERO_TLS_KEYFILE": material.keyPath,
            "FICHERO_TLS_SPKI_HASH": material.spkiPin
        ]
        if bonjourEnabled {
            environment["FICHERO_ENABLE_BONJOUR"] = "1"
        }
        return environment
    }
}

struct RemoteAccessTLSMaterial: Codable, Equatable {
    let bindHost: String
    let certificatePath: String
    let keyPath: String
    let spkiPin: String

    enum CodingKeys: String, CodingKey {
        case bindHost = "bind_host"
        case certificatePath = "certificate_path"
        case keyPath = "key_path"
        case spkiPin = "spki_pin"
    }
}

enum RemoteURLValidationError: LocalizedError, Equatable {
    case blank
    case invalid
    case unsupportedScheme
    case missingHost
    case insecureRemoteTransport
    case localhostNotAllowed
    case hostPolicyNotAllowed
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
        case .insecureRemoteTransport:
            return "Secure pairing needs HTTPS. Use a reachable HTTPS URL."
        case .localhostNotAllowed:
            return "Remote clients must use a non-localhost host."
        case .hostPolicyNotAllowed:
            return "Same-network hosting needs a literal IP address, .local hostname, or Tailscale .ts.net hostname."
        case .pathNotAllowed:
            return "Remote URLs must be the backend root, without a path."
        case .queryNotAllowed:
            return "Remote URLs cannot include a query string."
        case .fragmentNotAllowed:
            return "Remote URLs cannot include a fragment."
        }
    }
}

func validatedRemoteURL(
    from raw: String,
    allowLocalhost: Bool,
    requireSecureTransportForRemote: Bool = false
) throws -> URL {
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
    let normalizedHost = host.lowercased()
    let isLoopbackHost = EngineConfig.isLoopbackHostLiteral(normalizedHost)
    if requireSecureTransportForRemote, scheme != "https" {
        throw RemoteURLValidationError.insecureRemoteTransport
    }
    if !allowLocalhost, isLoopbackHost {
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

func validatedHostedRemoteURL(from raw: String) throws -> URL {
    let url = try validatedRemoteURL(
        from: raw,
        allowLocalhost: false,
        requireSecureTransportForRemote: true
    )
    guard hostedRemoteURLIsAllowed(url) else {
        throw RemoteURLValidationError.hostPolicyNotAllowed
    }
    return url
}

private func hostedRemoteURLIsAllowed(_ url: URL) -> Bool {
    guard let host = url.host?.lowercased(), !host.isEmpty else {
        return false
    }
    if host.hasSuffix(".local") {
        return true
    }
    if host.hasSuffix(".ts.net") {
        return true
    }
    return isIPAddressLiteral(host)
}

private func isIPAddressLiteral(_ host: String) -> Bool {
    var ipv4Address = in_addr()
    if host.withCString({ inet_pton(AF_INET, $0, &ipv4Address) }) == 1 {
        return true
    }

    var ipv6Address = in6_addr()
    if host.withCString({ inet_pton(AF_INET6, $0, &ipv6Address) }) == 1 {
        return true
    }

    return false
}

struct PairingQRCodePayload: Codable {
    let version: Int
    let apiURL: String
    let pairCode: String
    let expiresAt: Date
    let spki: String
    let libraryPath: String?

    enum CodingKeys: String, CodingKey {
        case version = "v"
        case apiURL = "api_url"
        case pairCode = "pair_code"
        case expiresAt = "expires_at"
        case spki
        case libraryPath = "library_path"
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

@MainActor
final class PairingService {
    private let client: FicheroClient

    init(apiRoot: URL) {
        self.client = FicheroClient(baseURL: apiRoot)
    }

    init(apiRoot: URL, expectedSPKIPin: String) throws {
        self.client = try FicheroClient(baseURL: apiRoot, expectedSPKIPin: expectedSPKIPin)
    }

    func createPairingCode() async throws -> PairingCodeRecord {
        let response = try await client.api.createPairingCodeApiPairCodePost(.init())
        switch response {
        case .ok(let okResponse):
            let record = try okResponse.body.json
            return PairingCodeRecord(code: record.code, expiresAt: record.expiresAt)
        case .undocumented(let statusCode, _):
            throw APIError.httpError(statusCode: statusCode, message: "Unexpected response")
        }
    }

    func listDevices() async throws -> [PairedDeviceRecord] {
        let response = try await client.api.listDevicesApiPairDevicesGet(.init())
        switch response {
        case .ok(let okResponse):
            let list = try okResponse.body.json
            return list.items.map { device in
                PairedDeviceRecord(
                    id: device.id,
                    name: device.name,
                    userId: device.userId,
                    createdAt: device.createdAt,
                    lastSeen: device.lastSeen,
                    expiresAt: device.expiresAt,
                    revoked: device.revoked
                )
            }
        case .undocumented(let statusCode, _):
            throw APIError.httpError(statusCode: statusCode, message: "Unexpected response")
        }
    }

    func revokeDevice(id: String) async throws {
        let response = try await client.api.revokeDeviceApiPairDevicesDeviceIdRevokePost(
            path: .init(deviceId: id)
        )
        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw APIError.httpError(statusCode: 422, message: detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw APIError.httpError(statusCode: statusCode, message: "Unexpected response")
        }
    }

    func pairDeviceUnauthenticated(code: String, deviceName: String) async throws -> PairingExchangeResponse {
        // `/api/pair` is accepted unauthenticated by the engine; the
        // AuthTokenMiddleware skips auth for this path so a local bootstrap
        // token is never forwarded to a remote host during pairing.
        let request = Components.Schemas.PairRequest(code: code, deviceName: deviceName)
        let response = try await client.api.pairDeviceApiPairPost(.init(body: .json(request)))
        switch response {
        case .ok(let okResponse):
            let record = try okResponse.body.json
            return PairingExchangeResponse(deviceId: record.deviceId, deviceToken: record.deviceToken)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw APIError.httpError(statusCode: 422, message: detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw APIError.httpError(statusCode: statusCode, message: "Unexpected response")
        }
    }

    func buildQRCodePayload(
        from code: PairingCodeRecord,
        spki: String = "",
        libraryPath: String? = nil
    ) -> PairingQRCodePayload {
        PairingQRCodePayload(
            version: 1,
            apiURL: client.baseURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")),
            pairCode: code.code,
            expiresAt: code.expiresAt,
            spki: spki,
            libraryPath: libraryPath
        )
    }

    static func persistAuthToken(_ token: String, for apiRoot: URL) throws {
        try AuthTokenMiddleware.persistRemoteToken(token, hostString: apiRoot.absoluteString)
    }
}
