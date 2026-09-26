import Darwin
import FicheroAPIClient
import Foundation

enum RemoteAccessConfig {
    /// Reads and writes go through this seam so tests can point the type at a
    /// throwaway suite instead of the developer's real app domain — see the
    /// note on `EngineConfig.defaults` (#4221). Production never assigns it.
    static var defaults: UserDefaults { EngineConfig.defaults }

    static let hostingEnabledKey = "fichero.remote_access.enabled"
    static let bonjourEnabledKey = "fichero.remote_access.bonjour_enabled"
    static let publicBaseURLKey = "fichero.remote_access.public_base_url"
    static let pairedLibraryPathKey = "fichero.remote_access.paired_library_path"

    static var hostingEnabled: Bool {
        defaults.bool(forKey: hostingEnabledKey)
    }

    static var bonjourEnabled: Bool {
        defaults.bool(forKey: bonjourEnabledKey)
    }

    static var publicBaseURLString: String {
        let stored = defaults.string(forKey: publicBaseURLKey) ?? ""
        return stored.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static var publicBaseURL: URL? {
        try? validatedHostedRemoteURL(from: publicBaseURLString)
    }

    static var advertisedSPKIPin: String {
        hostedBackendSPKIPin(hostString: publicBaseURLString) ?? ""
    }

    static func hostedBackendSPKIPin(hostString: String) -> String? {
        let trimmed = hostString.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        return RemoteCertificatePinning.advertisedSPKIPin(hostString: trimmed)
            ?? RemoteCertificatePinning.persistedSPKIPin(hostString: trimmed)
    }

    static var pairedLibraryPath: String {
        (defaults.string(forKey: pairedLibraryPathKey) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static var hasPairedLibraryPath: Bool {
        !pairedLibraryPath.isEmpty
    }

    /// Derives `https://<hostname>.local:<port>` from the system Bonjour name.
    /// The ONE home for the automatic address (#5042): the Share sheet and the
    /// Sharing settings pane both forward here, so they cannot drift apart.
    /// Port mirrors `EngineConfig.defaultHostString` so both stay in sync.
    static var autoLocalBaseURL: String {
        var host = ProcessInfo.processInfo.hostName.lowercased()
        if !host.hasSuffix(".local") {
            host = (host.components(separatedBy: ".").first ?? host) + ".local"
        }
        let port = URL(string: EngineConfig.defaultHostString)?.port ?? 8765
        return "https://\(host):\(port)"
    }

    /// Whether an advertised address can only be resolved from the same local
    /// network. A `.local` name is mDNS, and many managed networks — university
    /// campuses especially — do not resolve mDNS at all, so the link is
    /// well-formed and completely dead off-LAN (#5042).
    ///
    /// Name shape only. A Tailscale `.ts.net` name and a literal IP both resolve
    /// without mDNS, so neither is local-only by this test.
    ///
    /// Knows the same three-way host taxonomy as `hostedRemoteURLIsAllowed` below
    /// — `.local`, `.ts.net`, IP literal — for a different question: that one
    /// decides whether an address MAY be advertised, this one how far it reaches.
    /// Kept separate on purpose, but a fourth address kind has to be taught to
    /// BOTH, and nothing here will remind you.
    /// ponytail: no live reachability probe and no Tailscale auto-detection —
    /// rejected as over-built for #5042; the manual override already covers it.
    static func isLocalNetworkOnly(_ rawURLString: String) -> Bool {
        let trimmed = rawURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let host = URLComponents(string: trimmed)?.host?.lowercased(), !host.isEmpty else {
            return false
        }
        return host.hasSuffix(".local")
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

/// Whether a host may be advertised at all — the policy gate behind
/// `RemoteURLValidationError.hostPolicyNotAllowed`.
///
/// Shares its three-way taxonomy with `RemoteAccessConfig.isLocalNetworkOnly`
/// above, which asks the other question (how far the address reaches, not whether
/// it is allowed). A fourth address kind has to be taught to both.
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
