// swiftlint:disable file_length
import CryptoKit
import Foundation
#if canImport(Security)
import Security
#endif

public enum RemoteCertificatePinningError: LocalizedError, Equatable {
    case missingSPKIPin
    case invalidSPKIPin
    case serverTrustUnavailable
    case serverTrustEvaluationFailed
    case serverCertificateUnavailable
    case unsupportedPublicKey
    case serverIdentityMismatch

    public var errorDescription: String? {
        switch self {
        case .missingSPKIPin:
            return "Pairing requires a certificate SPKI pin."
        case .invalidSPKIPin:
            return "Enter a valid SPKI pin."
        case .serverTrustUnavailable:
            return "The host did not present a TLS certificate."
        case .serverTrustEvaluationFailed:
            return "Could not verify the host certificate."
        case .serverCertificateUnavailable:
            return "Could not read the host certificate."
        case .unsupportedPublicKey:
            return "The host certificate uses an unsupported public key type."
        case .serverIdentityMismatch:
            return "The host certificate does not match the expected SPKI pin."
        }
    }
}

// swiftlint:disable:next type_body_length
public enum RemoteCertificatePinning {
    public static let engineHostUserDefaultsKey = "fichero.engine.host"
    public static let legacyAdvertisedSPKIPinUserDefaultsKey = "fichero.remote_access.advertised_spki_pin"
    private static let advertisedSPKIPinUserDefaultsKeyPrefix = "fichero.remote_access.advertised_spki_pin|"
    private static let clientSPKIPinUserDefaultsKeyPrefix = "fichero.remote_access.client_spki_pin|"

    public static func shouldEnforcePinning(for baseURL: URL) -> Bool {
        guard let host = baseURL.host?.lowercased() else { return false }
        if persistedSPKIPin(hostString: baseURL.absoluteString) != nil {
            return true
        }
        if isLoopbackHostLiteral(host) {
            return false
        }
        return shouldEnforcePinning(forHost: host)
    }

    public static func validatedSPKIPin(_ raw: String) throws -> String {
        let collapsed = raw
            .components(separatedBy: .whitespacesAndNewlines)
            .joined()
        guard !collapsed.isEmpty else {
            throw RemoteCertificatePinningError.missingSPKIPin
        }

        if let prefixedHash = parsePrefixedSHA256Pin(collapsed) {
            return prefixedHash
        }
        if let digest = parseSHA256Digest(collapsed) {
            return "sha256/\(digest.base64EncodedString())"
        }
        if let rawSPKI = Data(base64Encoded: collapsed), !rawSPKI.isEmpty {
            return rawSPKI.base64EncodedString()
        }

        throw RemoteCertificatePinningError.invalidSPKIPin
    }

    public static func persistedSPKIPin(hostString: String? = nil) -> String? {
        let storageKey = clientSPKIPinUserDefaultsKey(hostString: hostString)
        guard let raw = UserDefaults.standard.string(forKey: storageKey) else {
            return nil
        }
        return try? validatedSPKIPin(raw)
    }

    public static func persistSPKIPin(_ raw: String, hostString: String? = nil) throws {
        let normalized = try validatedSPKIPin(raw)
        let storageKey = clientSPKIPinUserDefaultsKey(hostString: hostString)
        UserDefaults.standard.set(normalized, forKey: storageKey)
    }

    public static func clearPersistedSPKIPin(hostString: String? = nil) {
        let storageKey = clientSPKIPinUserDefaultsKey(hostString: hostString)
        UserDefaults.standard.removeObject(forKey: storageKey)
    }

    public static func advertisedSPKIPin(hostString: String? = nil) -> String? {
        let storageKey = advertisedSPKIPinUserDefaultsKey(hostString: hostString)
        guard let raw = UserDefaults.standard.string(forKey: storageKey) else {
            return nil
        }
        return try? validatedSPKIPin(raw)
    }

    public static func persistAdvertisedSPKIPin(_ raw: String, hostString: String? = nil) throws {
        let normalized = try validatedSPKIPin(raw)
        let storageKey = advertisedSPKIPinUserDefaultsKey(hostString: hostString)
        UserDefaults.standard.set(normalized, forKey: storageKey)
        UserDefaults.standard.removeObject(forKey: legacyAdvertisedSPKIPinUserDefaultsKey)
    }

    public static func persistHostedBackendSPKIPin(_ raw: String, hostString: String? = nil) throws {
        let normalized = try validatedSPKIPin(raw)
        let advertisedStorageKey = advertisedSPKIPinUserDefaultsKey(hostString: hostString)
        let clientStorageKey = clientSPKIPinUserDefaultsKey(hostString: hostString)
        UserDefaults.standard.set(normalized, forKey: advertisedStorageKey)
        UserDefaults.standard.set(normalized, forKey: clientStorageKey)
        UserDefaults.standard.removeObject(forKey: legacyAdvertisedSPKIPinUserDefaultsKey)
    }

    public static func clearAdvertisedSPKIPin(hostString: String? = nil) {
        let storageKey = advertisedSPKIPinUserDefaultsKey(hostString: hostString)
        UserDefaults.standard.removeObject(forKey: storageKey)
        if hostString == nil {
            UserDefaults.standard.removeObject(forKey: legacyAdvertisedSPKIPinUserDefaultsKey)
        }
    }

    public static func configuredSession(
        configuration: URLSessionConfiguration = .default
    ) -> URLSession {
        let sessionConfiguration = configuration.copy() as? URLSessionConfiguration ?? configuration
        return URLSession(
            configuration: sessionConfiguration,
            delegate: DynamicPinnedSessionDelegate(),
            delegateQueue: nil
        )
    }

    public static func pinnedSession(
        expectedSPKIPin rawSPKIPin: String,
        configuration: URLSessionConfiguration = .default
    ) throws -> URLSession {
        let normalizedSPKIPin = try validatedSPKIPin(rawSPKIPin)
        let sessionConfiguration = configuration.copy() as? URLSessionConfiguration ?? configuration
        return URLSession(
            configuration: sessionConfiguration,
            delegate: ExplicitPinnedSessionDelegate(expectedSPKIPin: normalizedSPKIPin),
            delegateQueue: nil
        )
    }

    #if canImport(Security)
    /// Resolve a server-trust authentication challenge against the dynamic
    /// (persisted-pin) policy, returning the disposition + credential the
    /// caller should hand to its completion handler.
    ///
    /// This is the single implementation of Fichero's server-trust pinning:
    /// the URLSession transport (`configuredSession`) AND the WKWebView reading
    /// / KG panes (`DocumentKGWebPane`) both route their challenges through it,
    /// so loopback + remote pinning behave identically regardless of which
    /// networking stack issues the request. Post-#2538 the loopback engine
    /// serves a self-signed pinned HTTPS cert; without this, WKWebView's
    /// default trust evaluation rejects it and the panes load nothing.
    public static func resolveServerTrustChallenge(
        _ challenge: URLAuthenticationChallenge
    ) -> (URLSession.AuthChallengeDisposition, URLCredential?) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust else {
            return (.performDefaultHandling, nil)
        }

        guard let trust = challenge.protectionSpace.serverTrust else {
            return (.cancelAuthenticationChallenge, nil)
        }
        let hostString = challengeHostString(challenge.protectionSpace)
        guard let expectedSPKIPin = persistedSPKIPin(hostString: hostString) else {
            let host = challenge.protectionSpace.host.lowercased()
            if isLoopbackChallengeHost(host) {
                if bootstrapLoopbackSPKIPin(from: trust, hostString: hostString) {
                    return (.useCredential, URLCredential(trust: trust))
                }
                return (.cancelAuthenticationChallenge, nil)
            }
            guard shouldEnforcePinning(forHost: host) else {
                return (.performDefaultHandling, nil)
            }
            return (.cancelAuthenticationChallenge, nil)
        }

        do {
            try validateServerTrust(
                trust,
                host: challenge.protectionSpace.host.lowercased(),
                expectedSPKIPin: expectedSPKIPin
            )
            return (.useCredential, URLCredential(trust: trust))
        } catch {
            let host = challenge.protectionSpace.host.lowercased()
            if isLoopbackChallengeHost(host),
               bootstrapLoopbackSPKIPin(from: trust, hostString: hostString) {
                return (.useCredential, URLCredential(trust: trust))
            }
            return (.cancelAuthenticationChallenge, nil)
        }
    }

    public static func validateServerTrust(
        _ trust: SecTrust,
        host: String,
        expectedSPKIPin: String
    ) throws {
        let normalizedSPKIPin = try validatedSPKIPin(expectedSPKIPin)
        let sslPolicy = SecPolicyCreateSSL(true, host as CFString)
        SecTrustSetPolicies(trust, sslPolicy)

        // Remote-access QR pairing intentionally allows a locally generated,
        // self-signed leaf certificate as long as the QR/persisted SPKI pin
        // matches. The pin is the trust root for this flow; CA validation is
        // still preserved for all unpinned traffic paths elsewhere.
        var trustError: CFError?
        _ = SecTrustEvaluateWithError(trust, &trustError)
        guard let certificate = SecTrustGetCertificateAtIndex(trust, 0) else {
            throw RemoteCertificatePinningError.serverCertificateUnavailable
        }
        try validateLeafCertificate(certificate, expectedSPKIPin: normalizedSPKIPin)
    }

    public static func validateLeafCertificate(
        _ certificate: SecCertificate,
        expectedSPKIPin: String
    ) throws {
        guard let publicKey = SecCertificateCopyKey(certificate) else {
            throw RemoteCertificatePinningError.serverCertificateUnavailable
        }
        try validatePublicKey(publicKey, expectedSPKIPin: expectedSPKIPin)
    }

    public static func validatePublicKey(
        _ key: SecKey,
        expectedSPKIPin: String
    ) throws {
        let normalizedSPKIPin = try validatedSPKIPin(expectedSPKIPin)
        let expectedPin = try normalizedExpectedPin(normalizedSPKIPin)
        let spkiData = try subjectPublicKeyInfo(for: key)

        switch expectedPin {
        case .sha256(let digest):
            let actualDigest = Data(SHA256.hash(data: spkiData))
            guard actualDigest == digest else {
                throw RemoteCertificatePinningError.serverIdentityMismatch
            }
        case .spki(let expectedSPKI):
            guard spkiData == expectedSPKI else {
                throw RemoteCertificatePinningError.serverIdentityMismatch
            }
        }
    }

    public static func spkiPin(for key: SecKey) throws -> String {
        let spkiData = try subjectPublicKeyInfo(for: key)
        return spkiData.base64EncodedString()
    }

    public static func sha256Pin(for key: SecKey) throws -> String {
        let spkiData = try subjectPublicKeyInfo(for: key)
        return "sha256/\(Data(SHA256.hash(data: spkiData)).base64EncodedString())"
    }

    private static func bootstrapLoopbackSPKIPin(from trust: SecTrust, hostString: String) -> Bool {
        guard let certificate = SecTrustGetCertificateAtIndex(trust, 0),
              let publicKey = SecCertificateCopyKey(certificate),
              let pin = try? spkiPin(for: publicKey) else {
            return false
        }
        do {
            try persistHostedBackendSPKIPin(pin, hostString: hostString)
            return true
        } catch {
            return false
        }
    }

    private static func normalizedExpectedPin(_ normalizedPin: String) throws -> ExpectedPin {
        if normalizedPin.hasPrefix("sha256/") {
            let digestBase64 = String(normalizedPin.dropFirst("sha256/".count))
            guard let digest = Data(base64Encoded: digestBase64), digest.count == 32 else {
                throw RemoteCertificatePinningError.invalidSPKIPin
            }
            return .sha256(digest)
        }

        guard let spki = Data(base64Encoded: normalizedPin), !spki.isEmpty else {
            throw RemoteCertificatePinningError.invalidSPKIPin
        }
        return .spki(spki)
    }

    private static func subjectPublicKeyInfo(for key: SecKey) throws -> Data {
        var exportError: Unmanaged<CFError>?
        guard let publicKeyData = SecKeyCopyExternalRepresentation(key, &exportError) as Data? else {
            throw RemoteCertificatePinningError.unsupportedPublicKey
        }

        guard let attributes = SecKeyCopyAttributes(key) as? [CFString: Any] else {
            throw RemoteCertificatePinningError.unsupportedPublicKey
        }
        guard let keyType = attributes[kSecAttrKeyType] else {
            throw RemoteCertificatePinningError.unsupportedPublicKey
        }
        let keySize = attributes[kSecAttrKeySizeInBits] as? Int

        let algorithmIdentifier: Data
        if CFEqual(keyType as CFTypeRef, kSecAttrKeyTypeRSA) {
            algorithmIdentifier = Data([
                0x30, 0x0D,
                0x06, 0x09, 0x2A, 0x86, 0x48, 0x86, 0xF7, 0x0D, 0x01, 0x01, 0x01,
                0x05, 0x00
            ])
        } else if CFEqual(keyType as CFTypeRef, kSecAttrKeyTypeECSECPrimeRandom)
            || CFEqual(keyType as CFTypeRef, kSecAttrKeyTypeEC) {
            switch keySize {
            case 256:
                algorithmIdentifier = Data([
                    0x30, 0x13,
                    0x06, 0x07, 0x2A, 0x86, 0x48, 0xCE, 0x3D, 0x02, 0x01,
                    0x06, 0x08, 0x2A, 0x86, 0x48, 0xCE, 0x3D, 0x03, 0x01, 0x07
                ])
            case 384:
                algorithmIdentifier = Data([
                    0x30, 0x10,
                    0x06, 0x07, 0x2A, 0x86, 0x48, 0xCE, 0x3D, 0x02, 0x01,
                    0x06, 0x05, 0x2B, 0x81, 0x04, 0x00, 0x22
                ])
            case 521:
                algorithmIdentifier = Data([
                    0x30, 0x10,
                    0x06, 0x07, 0x2A, 0x86, 0x48, 0xCE, 0x3D, 0x02, 0x01,
                    0x06, 0x05, 0x2B, 0x81, 0x04, 0x00, 0x23
                ])
            default:
                throw RemoteCertificatePinningError.unsupportedPublicKey
            }
        } else {
            throw RemoteCertificatePinningError.unsupportedPublicKey
        }

        let bitString = derBitString(publicKeyData)
        return derSequence([algorithmIdentifier, bitString])
    }

    private static func derSequence(_ components: [Data]) -> Data {
        let body = components.reduce(into: Data(), { partialResult, component in
            partialResult.append(component)
        })
        return derTag(0x30, body: body)
    }

    private static func derBitString(_ data: Data) -> Data {
        var body = Data([0x00])
        body.append(data)
        return derTag(0x03, body: body)
    }

    private static func derTag(_ tag: UInt8, body: Data) -> Data {
        var encoded = Data([tag])
        encoded.append(derLength(body.count))
        encoded.append(body)
        return encoded
    }

    private static func derLength(_ length: Int) -> Data {
        if length < 0x80 {
            return Data([UInt8(length)])
        }

        var value = length
        var bytes: [UInt8] = []
        while value > 0 {
            bytes.insert(UInt8(value & 0xFF), at: 0)
            value >>= 8
        }

        var encoded = Data([0x80 | UInt8(bytes.count)])
        encoded.append(contentsOf: bytes)
        return encoded
    }
    #endif

    private static func parsePrefixedSHA256Pin(_ raw: String) -> String? {
        let prefixes = ["sha256/", "sha256:"]
        guard let prefix = prefixes.first(where: { raw.lowercased().hasPrefix($0) }) else {
            return nil
        }
        let remainder = String(raw.dropFirst(prefix.count))
        guard let digest = parseSHA256Digest(remainder) else {
            return nil
        }
        return "sha256/\(digest.base64EncodedString())"
    }

    private static func parseSHA256Digest(_ raw: String) -> Data? {
        if let digest = parseHexDigest(raw) {
            return digest
        }
        guard let data = Data(base64Encoded: raw), data.count == 32 else {
            return nil
        }
        return data
    }

    private static func parseHexDigest(_ raw: String) -> Data? {
        guard raw.count == 64 else { return nil }
        var bytes = Data()
        bytes.reserveCapacity(32)

        var index = raw.startIndex
        while index < raw.endIndex {
            let nextIndex = raw.index(index, offsetBy: 2)
            let byteString = raw[index..<nextIndex]
            guard let byte = UInt8(byteString, radix: 16) else {
                return nil
            }
            bytes.append(byte)
            index = nextIndex
        }

        return bytes
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

    fileprivate static func shouldEnforcePinning(forHost host: String) -> Bool {
        if isLoopbackHostLiteral(host) {
            return persistedSPKIPin(hostString: "https://\(host):8765") != nil
        }
        if isTailscaleServeHost(host) {
            return false
        }
        return true
    }

    fileprivate static func isLoopbackChallengeHost(_ host: String) -> Bool {
        isLoopbackHostLiteral(host)
    }

    private static func isTailscaleServeHost(_ host: String) -> Bool {
        host.lowercased().hasSuffix(".ts.net")
    }

    private static func clientSPKIPinUserDefaultsKey(hostString: String? = nil) -> String {
        let normalizedHost = AuthTokenMiddleware.normalizedRemoteHostString(hostString: hostString)
        return "\(clientSPKIPinUserDefaultsKeyPrefix)\(normalizedHost)"
    }

    private static func advertisedSPKIPinUserDefaultsKey(hostString: String? = nil) -> String {
        let normalizedHost = AuthTokenMiddleware.normalizedRemoteHostString(hostString: hostString)
        return "\(advertisedSPKIPinUserDefaultsKeyPrefix)\(normalizedHost)"
    }

    fileprivate static func challengeHostString(_ protectionSpace: URLProtectionSpace) -> String {
        let scheme = protectionSpace.protocol?.lowercased() ?? "https"
        var components = URLComponents()
        components.scheme = scheme
        components.host = protectionSpace.host.lowercased()
        let port = protectionSpace.port
        if port > 0,
           !((scheme == "https" && port == 443) || (scheme == "http" && port == 80)) {
            components.port = port
        }
        return components.string ?? "\(scheme)://\(protectionSpace.host.lowercased())"
    }
}

private enum ExpectedPin {
    case spki(Data)
    case sha256(Data)
}

#if canImport(Security)
private final class ExplicitPinnedSessionDelegate: NSObject, URLSessionDelegate {
    private let expectedSPKIPin: String

    init(expectedSPKIPin: String) {
        self.expectedSPKIPin = expectedSPKIPin
    }

    func urlSession(
        _ session: URLSession,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping @Sendable (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust else {
            completionHandler(.performDefaultHandling, nil)
            return
        }

        guard let trust = challenge.protectionSpace.serverTrust else {
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }

        do {
            try RemoteCertificatePinning.validateServerTrust(
                trust,
                host: challenge.protectionSpace.host,
                expectedSPKIPin: expectedSPKIPin
            )
            completionHandler(.useCredential, URLCredential(trust: trust))
        } catch {
            completionHandler(.cancelAuthenticationChallenge, nil)
        }
    }
}

// Conforms to BOTH URLSessionDelegate (session-level challenge, used by regular
// request/response) AND URLSessionTaskDelegate (task-level challenge). The task
// conformance is REQUIRED for `URLSession.bytes(for:)` SSE streams: URLSession
// routes a stream's server-trust challenge to the TASK-level method, which it
// only invokes when the delegate formally conforms to URLSessionTaskDelegate.
// Implementing the method without declaring the conformance (the #2960/B4 bug)
// left `.bytes` streams on default trust → self-signed 127.0.0.1 rejected (-9807).
internal final class DynamicPinnedSessionDelegate: NSObject, URLSessionDelegate, URLSessionTaskDelegate {
    func urlSession(
        _ session: URLSession,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping @Sendable (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        let (disposition, credential) = RemoteCertificatePinning.resolveServerTrustChallenge(challenge)
        completionHandler(disposition, credential)
    }

    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping @Sendable (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        let (disposition, credential) = RemoteCertificatePinning.resolveServerTrustChallenge(challenge)
        completionHandler(disposition, credential)
    }
}
#endif
