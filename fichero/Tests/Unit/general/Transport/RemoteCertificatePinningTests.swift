import Foundation
#if canImport(Security)
import Security
#endif
@testable import FicheroAPIClient
import XCTest

final class RemoteCertificatePinningTests: XCTestCase {
    private let hostOne = "https://host-one.tailnet.example"
    private let hostTwo = "https://host-two.tailnet.example:8443"
    private let hostOneDefaultPort = "https://host-one.tailnet.example:443/api"
    private let hostedBackendHost = "https://pairing.example.com:9443"
    private let tailscaleServeHost = "https://studio.tailnet-name.ts.net"
    private let advertisedPin = Data("advertised-spki".utf8).base64EncodedString()
    private let hostOnePin = Data("host-one-spki".utf8).base64EncodedString()
    private let hostTwoPin = Data("host-two-spki".utf8).base64EncodedString()

    override func tearDown() {
        super.tearDown()
        RemoteCertificatePinning.clearAdvertisedSPKIPin(hostString: hostOne)
        RemoteCertificatePinning.clearAdvertisedSPKIPin(hostString: hostTwo)
        RemoteCertificatePinning.clearAdvertisedSPKIPin(hostString: hostedBackendHost)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostOne)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostTwo)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostedBackendHost)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: tailscaleServeHost)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostOneDefaultPort)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: "https://127.0.0.1:8765")
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: "https://pairing.example.com")
    }

    func testValidatedSPKIPinRejectsMissingPin() {
        XCTAssertThrowsError(try RemoteCertificatePinning.validatedSPKIPin("   ")) { error in
            XCTAssertEqual(error as? RemoteCertificatePinningError, .missingSPKIPin)
        }
    }

    func testValidatedSPKIPinCanonicalizesSHA256Forms() throws {
        let digest = Data(repeating: 0xAB, count: 32)
        let base64 = digest.base64EncodedString()
        let hex = digest.map { String(format: "%02x", $0) }.joined()

        XCTAssertEqual(
            try RemoteCertificatePinning.validatedSPKIPin("sha256:\(base64)"),
            "sha256/\(base64)"
        )
        XCTAssertEqual(
            try RemoteCertificatePinning.validatedSPKIPin(hex),
            "sha256/\(base64)"
        )
    }

    func testLoopbackHTTPSUsesPinningOnlyWhenPinned() throws {
        let loopbackHost = "https://127.0.0.1:8765"
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: loopbackHost)

        XCTAssertFalse(RemoteCertificatePinning.shouldEnforcePinning(for: URL(string: loopbackHost)!))

        try RemoteCertificatePinning.persistSPKIPin(hostOnePin, hostString: loopbackHost)

        XCTAssertTrue(RemoteCertificatePinning.shouldEnforcePinning(for: URL(string: loopbackHost)!))
        XCTAssertTrue(RemoteCertificatePinning.shouldEnforcePinning(for: URL(string: "https://host.tailnet.example")!))
    }

    func testTailscaleServeHostsUseDefaultTrustUnlessPinned() throws {
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: tailscaleServeHost)

        XCTAssertFalse(RemoteCertificatePinning.shouldEnforcePinning(for: URL(string: tailscaleServeHost)!))

        try RemoteCertificatePinning.persistSPKIPin(hostOnePin, hostString: tailscaleServeHost)

        XCTAssertTrue(RemoteCertificatePinning.shouldEnforcePinning(for: URL(string: tailscaleServeHost)!))
    }

    func testPersistedSPKIPinsAreHostScoped() throws {
        try RemoteCertificatePinning.persistSPKIPin(hostOnePin, hostString: hostOne)
        try RemoteCertificatePinning.persistSPKIPin(hostTwoPin, hostString: hostTwo)

        XCTAssertEqual(RemoteCertificatePinning.persistedSPKIPin(hostString: hostOne), hostOnePin)
        XCTAssertEqual(RemoteCertificatePinning.persistedSPKIPin(hostString: hostTwo), hostTwoPin)

        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostOne)

        XCTAssertNil(RemoteCertificatePinning.persistedSPKIPin(hostString: hostOne))
        XCTAssertEqual(RemoteCertificatePinning.persistedSPKIPin(hostString: hostTwo), hostTwoPin)
    }

    func testAdvertisedSPKIPinIsStoredSeparatelyFromClientPins() throws {
        try RemoteCertificatePinning.persistAdvertisedSPKIPin(advertisedPin, hostString: hostOne)
        try RemoteCertificatePinning.persistSPKIPin(hostOnePin, hostString: hostOne)

        XCTAssertEqual(RemoteCertificatePinning.advertisedSPKIPin(hostString: hostOne), advertisedPin)
        XCTAssertEqual(RemoteCertificatePinning.persistedSPKIPin(hostString: hostOne), hostOnePin)
    }

    func testHostedBackendSPKIPinIsAvailableToBothQRAndClientSessions() throws {
        try RemoteCertificatePinning.persistHostedBackendSPKIPin(advertisedPin, hostString: hostedBackendHost)

        XCTAssertEqual(RemoteCertificatePinning.advertisedSPKIPin(hostString: hostedBackendHost), advertisedPin)
        XCTAssertEqual(RemoteCertificatePinning.persistedSPKIPin(hostString: hostedBackendHost), advertisedPin)
    }

    func testPersistedPinsNormalizeExplicitDefaultPorts() throws {
        try RemoteCertificatePinning.persistSPKIPin(hostOnePin, hostString: hostOneDefaultPort)
        try RemoteCertificatePinning.persistAdvertisedSPKIPin(advertisedPin, hostString: hostOneDefaultPort)

        XCTAssertEqual(RemoteCertificatePinning.persistedSPKIPin(hostString: hostOne), hostOnePin)
        XCTAssertEqual(RemoteCertificatePinning.advertisedSPKIPin(hostString: hostOne), advertisedPin)
    }

    #if canImport(Security)
    func testValidatePublicKeyMatchesRawSPKIAndSHA256Pins() throws {
        let attributes: [String: Any] = [
            kSecAttrKeyType as String: kSecAttrKeyTypeECSECPrimeRandom,
            kSecAttrKeySizeInBits as String: 256
        ]
        var error: Unmanaged<CFError>?
        let privateKey = try XCTUnwrap(SecKeyCreateRandomKey(attributes as CFDictionary, &error))
        let publicKey = try XCTUnwrap(SecKeyCopyPublicKey(privateKey))

        let rawPin = try RemoteCertificatePinning.spkiPin(for: publicKey)
        let sha256Pin = try RemoteCertificatePinning.sha256Pin(for: publicKey)

        XCTAssertNoThrow(try RemoteCertificatePinning.validatePublicKey(publicKey, expectedSPKIPin: rawPin))
        XCTAssertNoThrow(try RemoteCertificatePinning.validatePublicKey(publicKey, expectedSPKIPin: sha256Pin))

        let wrongPin = "sha256/\(Data(repeating: 0xCD, count: 32).base64EncodedString())"
        XCTAssertThrowsError(try RemoteCertificatePinning.validatePublicKey(publicKey, expectedSPKIPin: wrongPin)) { error in
            XCTAssertEqual(error as? RemoteCertificatePinningError, .serverIdentityMismatch)
        }
    }

    func testValidateServerTrustAcceptsPinnedSelfSignedCertificate() throws {
        let trustContext = try SelfSignedTrustFixture.makeTrust()

        XCTAssertNoThrow(
            try RemoteCertificatePinning.validateServerTrust(
                trustContext.trust,
                host: trustContext.host,
                expectedSPKIPin: trustContext.spkiPin
            )
        )
    }

    func testValidateServerTrustRejectsPinnedSelfSignedCertificateWithWrongPin() throws {
        let trustContext = try SelfSignedTrustFixture.makeTrust()
        let wrongPin = Data("wrong-pin".utf8).base64EncodedString()

        XCTAssertThrowsError(
            try RemoteCertificatePinning.validateServerTrust(
                trustContext.trust,
                host: trustContext.host,
                expectedSPKIPin: wrongPin
            )
        ) { error in
            XCTAssertEqual(error as? RemoteCertificatePinningError, .serverIdentityMismatch)
        }
    }

    func testConfiguredSessionDelegateAcceptsPinnedSelfSignedCertificate() throws {
        let trustContext = try SelfSignedTrustFixture.makeTrust()
        let hostString = "https://\(trustContext.host)"
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostString)
        try RemoteCertificatePinning.persistSPKIPin(trustContext.spkiPin, hostString: hostString)

        let delegate = DynamicPinnedSessionDelegate()
        let protectionSpace = MockServerTrustProtectionSpace(
            host: trustContext.host,
            port: 443,
            protocol: "https",
            realm: nil,
            authenticationMethod: NSURLAuthenticationMethodServerTrust,
            serverTrust: trustContext.trust
        )
        let sender = MockChallengeSender()
        let challenge = MockServerTrustChallenge(
            protectionSpace: protectionSpace,
            proposedCredential: nil,
            previousFailureCount: 0,
            failureResponse: nil,
            error: nil,
            sender: sender
        )

        let expectation = self.expectation(description: "challenge completion")
        let capture = ChallengeCapture()
        delegate.urlSession(URLSession.shared, didReceive: challenge) { disposition, credential in
            capture.set(disposition: disposition, credential: credential)
            expectation.fulfill()
        }
        wait(for: [expectation], timeout: 1.0)

        XCTAssertEqual(capture.disposition, .useCredential)
        XCTAssertNotNil(capture.credential)
    }

    /// #2960/B4 regression: the delegate must FORMALLY conform to
    /// URLSessionTaskDelegate, not merely implement the task-level challenge
    /// method. `URLSession.bytes(for:)` routes a stream's server-trust challenge
    /// to the task-level method only when the delegate conforms to the protocol;
    /// implementing-without-conforming left SSE streams on default trust and the
    /// self-signed 127.0.0.1 cert was rejected with -9807. The existing
    /// `...TaskDelegateAcceptsPinnedSelfSignedCertificate` test calls the method
    /// directly, so it passes even without the conformance — this guards the
    /// conformance that actually enables bytes-stream routing.
    func testConfiguredSessionDelegateConformsToTaskDelegate() {
        // Typed as `Any` so the `is` check is a genuine runtime conformance test
        // (a concrete-typed value would let the compiler fold it to a constant and
        // warn "always true"); this still fails if the conformance is removed.
        let delegate: Any = DynamicPinnedSessionDelegate()
        XCTAssertTrue(
            delegate is URLSessionTaskDelegate,
            "DynamicPinnedSessionDelegate must conform to URLSessionTaskDelegate so "
                + "URLSession.bytes(for:) fires the cert-pin challenge for SSE streams (#2960/B4)"
        )
    }

    func testConfiguredSessionTaskDelegateAcceptsPinnedSelfSignedCertificate() throws {
        let trustContext = try SelfSignedTrustFixture.makeTrust()
        let hostString = "https://\(trustContext.host)"
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostString)
        try RemoteCertificatePinning.persistSPKIPin(trustContext.spkiPin, hostString: hostString)

        let capture = try captureChallenge(
            host: trustContext.host,
            port: 443,
            trust: trustContext.trust,
            useTaskDelegate: true
        )

        XCTAssertEqual(capture.disposition, .useCredential)
        XCTAssertNotNil(capture.credential)
    }

    func testConfiguredSessionDelegateBootstrapsLoopbackPin() throws {
        let trustContext = try SelfSignedTrustFixture.makeTrust()
        let hostString = "https://127.0.0.1:8765"
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostString)

        let capture = try captureChallenge(
            host: "127.0.0.1",
            port: 8765,
            trust: trustContext.trust
        )

        XCTAssertEqual(capture.disposition, .useCredential)
        XCTAssertNotNil(capture.credential)
        XCTAssertEqual(RemoteCertificatePinning.persistedSPKIPin(hostString: hostString), trustContext.spkiPin)
    }

    func testConfiguredSessionDelegateRefreshesStaleLoopbackPin() throws {
        let trustContext = try SelfSignedTrustFixture.makeTrust()
        let hostString = "https://127.0.0.1:8765"
        let stalePin = Data("stale-loopback-pin".utf8).base64EncodedString()
        try RemoteCertificatePinning.persistSPKIPin(stalePin, hostString: hostString)

        let capture = try captureChallenge(
            host: "127.0.0.1",
            port: 8765,
            trust: trustContext.trust
        )

        XCTAssertEqual(capture.disposition, .useCredential)
        XCTAssertNotNil(capture.credential)
        XCTAssertEqual(RemoteCertificatePinning.persistedSPKIPin(hostString: hostString), trustContext.spkiPin)
    }
    #endif
}

#if canImport(Security)
private func captureChallenge(
    host: String,
    port: Int,
    trust: SecTrust,
    useTaskDelegate: Bool = false
) throws -> ChallengeCapture {
    let delegate = DynamicPinnedSessionDelegate()
    let protectionSpace = MockServerTrustProtectionSpace(
        host: host,
        port: port,
        protocol: "https",
        realm: nil,
        authenticationMethod: NSURLAuthenticationMethodServerTrust,
        serverTrust: trust
    )
    let sender = MockChallengeSender()
    let challenge = MockServerTrustChallenge(
        protectionSpace: protectionSpace,
        proposedCredential: nil,
        previousFailureCount: 0,
        failureResponse: nil,
        error: nil,
        sender: sender
    )

    let expectation = XCTestExpectation(description: "challenge completion")
    let capture = ChallengeCapture()
    if useTaskDelegate {
        let task = URLSession.shared.dataTask(with: URL(string: "https://\(host)")!)
        delegate.urlSession(URLSession.shared, task: task, didReceive: challenge) { disposition, credential in
            capture.set(disposition: disposition, credential: credential)
            expectation.fulfill()
        }
    } else {
        delegate.urlSession(URLSession.shared, didReceive: challenge) { disposition, credential in
            capture.set(disposition: disposition, credential: credential)
            expectation.fulfill()
        }
    }
    _ = XCTWaiter.wait(for: [expectation], timeout: 1.0)
    return capture
}

private final class MockServerTrustProtectionSpace: URLProtectionSpace, @unchecked Sendable {
    private let testServerTrust: SecTrust?

    override var serverTrust: SecTrust? { testServerTrust }

    init(
        host: String,
        port: Int,
        protocol scheme: String?,
        realm: String?,
        authenticationMethod: String,
        serverTrust: SecTrust?
    ) {
        self.testServerTrust = serverTrust
        super.init(host: host, port: port, protocol: scheme, realm: realm, authenticationMethod: authenticationMethod)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
}

private final class MockServerTrustChallenge: URLAuthenticationChallenge, @unchecked Sendable {
    private let testProtectionSpace: URLProtectionSpace

    override var protectionSpace: URLProtectionSpace { testProtectionSpace }

    override init(
        protectionSpace: URLProtectionSpace,
        proposedCredential: URLCredential?,
        previousFailureCount: Int,
        failureResponse: URLResponse?,
        error: Error?,
        sender: URLAuthenticationChallengeSender
    ) {
        self.testProtectionSpace = protectionSpace
        super.init(
            protectionSpace: protectionSpace,
            proposedCredential: proposedCredential,
            previousFailureCount: previousFailureCount,
            failureResponse: failureResponse,
            error: error,
            sender: sender
        )
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
}

private final class MockChallengeSender: NSObject, URLAuthenticationChallengeSender {
    func use(_ credential: URLCredential, for challenge: URLAuthenticationChallenge) {}
    func continueWithoutCredential(for challenge: URLAuthenticationChallenge) {}
    func cancel(_ challenge: URLAuthenticationChallenge) {}
    func rejectProtectionSpaceAndContinue(with challenge: URLAuthenticationChallenge) {}
}

private enum SelfSignedTrustFixture {
    private static let certificatePEM = """
    -----BEGIN CERTIFICATE-----
    MIIBsjCCAVigAwIBAgIUKq7jMn7Md6TrOFgBs2n+UOTcStQwCgYIKoZIzj0EAwIw
    HjEcMBoGA1UEAwwTcGFpcmluZy5leGFtcGxlLmNvbTAeFw0yNjA2MjAwMjEwNTda
    Fw0zNjA2MTcwMjEwNTdaMB4xHDAaBgNVBAMME3BhaXJpbmcuZXhhbXBsZS5jb20w
    WTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAATtX7g1xvgqa6sHVGbnKRVqjlblLvH9
    zCSGG1vBICt8n/BksZre3ZA0Ys9xcdQeXKn5JSd2erCtSvNAnMLPvjxco3QwcjAe
    BgNVHREEFzAVghNwYWlyaW5nLmV4YW1wbGUuY29tMAwGA1UdEwEB/wQCMAAwDgYD
    VR0PAQH/BAQDAgWgMBMGA1UdJQQMMAoGCCsGAQUFBwMBMB0GA1UdDgQWBBQF5zYh
    4ZbjbccvXv/Q5lIEIBxC0jAKBggqhkjOPQQDAgNIADBFAiEA6ylvFxOS10LqtJuf
    TuVXtPUbqmtyFyFQOMg0jJuXC9kCIG35tnzQEvkWauYH4PSBJXT5JxOH/N/Hqu1Q
    ssceEo99
    -----END CERTIFICATE-----
    """

    struct TrustContext {
        let trust: SecTrust
        let host: String
        let spkiPin: String
    }

    static func makeTrust() throws -> TrustContext {
        let certificate = try certificate()
        let host = "pairing.example.com"
        let policy = SecPolicyCreateSSL(true, host as CFString)
        var optionalTrust: SecTrust?
        let status = SecTrustCreateWithCertificates([certificate] as CFArray, policy, &optionalTrust)
        XCTAssertEqual(status, errSecSuccess)
        let trust = try XCTUnwrap(optionalTrust)
        let publicKey = try XCTUnwrap(SecCertificateCopyKey(certificate))
        let spkiPin = try RemoteCertificatePinning.spkiPin(for: publicKey)
        return TrustContext(trust: trust, host: host, spkiPin: spkiPin)
    }

    private static func certificate() throws -> SecCertificate {
        let base64Body = certificatePEM
            .components(separatedBy: .newlines)
            .filter { !$0.hasPrefix("-----") && !$0.isEmpty }
            .joined()
        let derData = try XCTUnwrap(Data(base64Encoded: base64Body))
        return try XCTUnwrap(SecCertificateCreateWithData(nil, derData as CFData))
    }
}

private final class ChallengeCapture: @unchecked Sendable {
    private let lock = NSLock()
    private var capturedDisposition: URLSession.AuthChallengeDisposition?
    private var capturedCredential: URLCredential?

    var disposition: URLSession.AuthChallengeDisposition? {
        lock.lock()
        defer { lock.unlock() }
        return capturedDisposition
    }

    var credential: URLCredential? {
        lock.lock()
        defer { lock.unlock() }
        return capturedCredential
    }

    func set(disposition: URLSession.AuthChallengeDisposition, credential: URLCredential?) {
        lock.lock()
        capturedDisposition = disposition
        capturedCredential = credential
        lock.unlock()
    }
}
#endif
