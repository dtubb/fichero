import FicheroAPIClient
import Foundation
import XCTest

@testable import Fichero

@MainActor
final class RemoteAccessConfigTests: XCTestCase {
    private let validSPKIPin = Data("spki-value".utf8).base64EncodedString()
    private let previousHost = "https://previous.tailnet.example"
    private let attemptedHost = URL(string: "https://attempted.tailnet.example:8443")!

    override func tearDown() {
        super.tearDown()
        AuthTokenMiddleware.clearRemoteToken(hostString: previousHost)
        AuthTokenMiddleware.clearRemoteToken(hostString: attemptedHost.absoluteString)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: previousHost)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: attemptedHost.absoluteString)
        UserDefaults.standard.removeObject(forKey: EngineConfig.userDefaultsKey)
    }

    func testPairingBackendURLUsesAdvertisedRoot() throws {
        let advertised = "  https://pairing.example.com/  "
        let pairingURL = try XCTUnwrap(RemoteAccessConfig.pairingBackendURL(from: advertised))
        XCTAssertEqual(pairingURL.absoluteString, "https://pairing.example.com")

        let code = PairingCodeRecord(
            code: "PAIR-1234",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService(apiRoot: pairingURL).buildQRCodePayload(from: code, spki: validSPKIPin)

        XCTAssertEqual(payload.apiURL, "https://pairing.example.com")
        XCTAssertEqual(payload.pairCode, "PAIR-1234")
        XCTAssertEqual(payload.spki, validSPKIPin)
        XCTAssertEqual(payload.expiresAt, code.expiresAt)
    }

    func testPairingQRCodePayloadDecoderRoundTripsRemoteHost() throws {
        let apiRoot = URL(string: "https://pairing.example.com/")!
        let code = PairingCodeRecord(
            code: "PAIR-1234",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService(apiRoot: apiRoot).buildQRCodePayload(from: code, spki: validSPKIPin)

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let message = try XCTUnwrap(String(bytes: encoder.encode(payload), encoding: .utf8))
        let decoded = try PairingQRCodePayloadDecoder.decode(message: message)

        XCTAssertEqual(decoded.version, 1)
        XCTAssertEqual(decoded.apiURL, "https://pairing.example.com")
        XCTAssertEqual(decoded.pairCode, code.code)
        XCTAssertEqual(decoded.spki, validSPKIPin)
        XCTAssertEqual(decoded.expiresAt, code.expiresAt)
    }

    func testRemoteClientPairingFieldsNormalizeRemoteHost() throws {
        let apiRoot = URL(string: "https://pairing.example.com/")!
        let code = PairingCodeRecord(
            code: "PAIR-1234",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService(apiRoot: apiRoot).buildQRCodePayload(from: code, spki: validSPKIPin)

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let message = try XCTUnwrap(String(bytes: encoder.encode(payload), encoding: .utf8))
        let pairingFields = try RemoteClientPairing.pairingFields(from: message)

        XCTAssertEqual(pairingFields.remoteURL, "https://pairing.example.com")
        XCTAssertEqual(pairingFields.pairCode, "PAIR-1234")
        XCTAssertEqual(pairingFields.spkiPin, validSPKIPin)
    }

    func testRemoteClientPairingFieldsRejectLocalhostPayloads() throws {
        let apiRoot = URL(string: "http://127.0.0.1:8765/")!
        let code = PairingCodeRecord(
            code: "PAIR-1234",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService(apiRoot: apiRoot).buildQRCodePayload(from: code, spki: validSPKIPin)

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let message = try XCTUnwrap(String(bytes: encoder.encode(payload), encoding: .utf8))

        XCTAssertThrowsError(try RemoteClientPairing.pairingFields(from: message)) { error in
            XCTAssertEqual(error as? RemoteURLValidationError, .localhostNotAllowed)
        }
    }

    func testRemoteClientPairingFieldsRejectMissingSPKIPayload() throws {
        let apiRoot = URL(string: "https://pairing.example.com/")!
        let code = PairingCodeRecord(
            code: "PAIR-1234",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService(apiRoot: apiRoot).buildQRCodePayload(from: code, spki: "")

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let message = try XCTUnwrap(String(bytes: encoder.encode(payload), encoding: .utf8))

        XCTAssertThrowsError(try RemoteClientPairing.pairingFields(from: message)) { error in
            XCTAssertEqual(error as? RemoteCertificatePinningError, .missingSPKIPin)
        }
    }

    func testRemoteClientPairingAcceptsHealthyHealthStatus() {
        XCTAssertTrue(RemoteClientPairing.isAcceptableHealthStatus("healthy"))
        XCTAssertTrue(RemoteClientPairing.isAcceptableHealthStatus("HEALTHY"))
        XCTAssertTrue(RemoteClientPairing.isAcceptableHealthStatus("ok"))
        XCTAssertFalse(RemoteClientPairing.isAcceptableHealthStatus("unhealthy"))
    }

    func testRollbackFailedHostSwitchRestoresPreviousHostAndClearsAttemptedTrustMaterial() throws {
        try AuthTokenMiddleware.persistRemoteToken("previous-token", hostString: previousHost)
        try AuthTokenMiddleware.persistRemoteToken("attempted-token", hostString: attemptedHost.absoluteString)
        try RemoteCertificatePinning.persistSPKIPin(validSPKIPin, hostString: previousHost)
        try RemoteCertificatePinning.persistSPKIPin(
            Data("attempted-spki".utf8).base64EncodedString(),
            hostString: attemptedHost.absoluteString
        )
        UserDefaults.standard.set(attemptedHost.absoluteString, forKey: EngineConfig.userDefaultsKey)

        RemoteClientPairing.rollbackFailedHostSwitch(previousHost: previousHost, attemptedHost: attemptedHost)

        XCTAssertEqual(UserDefaults.standard.string(forKey: EngineConfig.userDefaultsKey), previousHost)
        XCTAssertEqual(AuthTokenMiddleware.readRemoteTokenForHost(previousHost), "previous-token")
        XCTAssertEqual(RemoteCertificatePinning.persistedSPKIPin(hostString: previousHost), validSPKIPin)
        XCTAssertNil(AuthTokenMiddleware.readRemoteTokenForHost(attemptedHost.absoluteString))
        XCTAssertNil(RemoteCertificatePinning.persistedSPKIPin(hostString: attemptedHost.absoluteString))
    }

    func testPairingBackendURLRejectsBlankString() {
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: ""))
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: "   "))
    }

    func testPairingBackendURLRejectsLocalhostAndPaths() {
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: "http://127.0.0.1:8765"))
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: "http://127.2.3.4:8765"))
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: "http://[::1]:8765"))
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: "http://[::ffff:127.0.0.1]:8765"))
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: "http://pairing.example.com"))
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: "https://pairing.example.com/api"))
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: "https://pairing.example.com?foo=bar"))
    }

    func testValidatedRemoteURLNormalizesReachableRoot() throws {
        let url = try validatedRemoteURL(from: " https://pairing.example.com/ ", allowLocalhost: false)
        XCTAssertEqual(url.absoluteString, "https://pairing.example.com")
    }

    func testValidatedRemoteURLRejectsUnsupportedSchemes() {
        XCTAssertThrowsError(try validatedRemoteURL(from: "ftp://pairing.example.com", allowLocalhost: false)) { error in
            XCTAssertEqual(error as? RemoteURLValidationError, .unsupportedScheme)
        }
    }

    func testValidatedRemoteURLRejectsRemoteHTTPWhenSecureTransportRequired() {
        XCTAssertThrowsError(
            try validatedRemoteURL(
                from: "http://pairing.example.com",
                allowLocalhost: false,
                requireSecureTransportForRemote: true
            )
        ) { error in
            XCTAssertEqual(error as? RemoteURLValidationError, .insecureRemoteTransport)
        }
    }

    func testInsecureRemoteTransportExplainsHttpsRequirement() {
        let message = RemoteURLValidationError.insecureRemoteTransport.errorDescription ?? ""

        XCTAssertTrue(message.contains("HTTPS"))
        XCTAssertTrue(message.contains("Tailscale HTTPS"))
    }

    func testActivePairedDevicesFilterHidesRevokedDevices() {
        let active = PairedDeviceRecord(
            id: "active",
            name: "Active Device",
            userId: "user-1",
            createdAt: Date(timeIntervalSince1970: 1_700_000_000),
            lastSeen: Date(timeIntervalSince1970: 1_700_000_100),
            expiresAt: Date(timeIntervalSince1970: 1_700_000_200),
            revoked: false
        )
        let revoked = PairedDeviceRecord(
            id: "revoked",
            name: "Revoked Device",
            userId: "user-1",
            createdAt: Date(timeIntervalSince1970: 1_700_000_300),
            lastSeen: Date(timeIntervalSince1970: 1_700_000_400),
            expiresAt: Date(timeIntervalSince1970: 1_700_000_500),
            revoked: true
        )

        let visibleDevices = activePairedDevices(from: [revoked, active])

        XCTAssertEqual(visibleDevices.map(\.id), ["active"])
    }

    func testValidatedRemoteURLAllowsLocalhostHTTPWhenExplicitlyAllowed() throws {
        let url = try validatedRemoteURL(
            from: "http://127.0.0.1:8765",
            allowLocalhost: true,
            requireSecureTransportForRemote: true
        )
        XCTAssertEqual(url.absoluteString, "http://127.0.0.1:8765")
    }

    func testValidatedRemoteURLAcceptsHTTPSWhenSecureTransportRequired() throws {
        let url = try validatedRemoteURL(
            from: "https://pairing.example.com",
            allowLocalhost: false,
            requireSecureTransportForRemote: true
        )
        XCTAssertEqual(url.absoluteString, "https://pairing.example.com")
    }
}
