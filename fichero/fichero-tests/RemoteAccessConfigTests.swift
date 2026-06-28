import FicheroAPIClient
import Foundation
import XCTest

@testable import Fichero

// swiftlint:disable type_body_length
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
        UserDefaults.standard.removeObject(forKey: RemoteAccessConfig.hostingEnabledKey)
        UserDefaults.standard.removeObject(forKey: RemoteAccessConfig.publicBaseURLKey)
        UserDefaults.standard.removeObject(forKey: RemoteAccessConfig.pairedLibraryPathKey)
        UserDefaults.standard.removeObject(forKey: EngineConfig.multiuserEnabledKey)
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
        let payload = PairingService(apiRoot: pairingURL).buildQRCodePayload(
            from: code,
            spki: validSPKIPin,
            libraryPath: "/Users/daniel/Archives/Open.fichero"
        )

        XCTAssertEqual(payload.apiURL, "https://pairing.example.com")
        XCTAssertEqual(payload.pairCode, "PAIR-1234")
        XCTAssertEqual(payload.spki, validSPKIPin)
        XCTAssertEqual(payload.expiresAt, code.expiresAt)
        XCTAssertEqual(payload.libraryPath, "/Users/daniel/Archives/Open.fichero")
    }

    func testHostedRemoteURLAcceptsTailscaleMagicDNSHost() throws {
        let url = try validatedHostedRemoteURL(from: " https://studio.tailnet-name.ts.net/ ")

        XCTAssertEqual(url.absoluteString, "https://studio.tailnet-name.ts.net")
    }

    func testPairingPayloadCanAdvertiseTailnetHost() throws {
        let pairingURL = try XCTUnwrap(
            RemoteAccessConfig.pairingBackendURL(from: "https://studio.tailnet-name.ts.net")
        )
        let code = PairingCodeRecord(
            code: "PAIR-2400",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService(apiRoot: pairingURL).buildQRCodePayload(
            from: code,
            spki: validSPKIPin,
            libraryPath: "/Users/daniel/Archives/Open.fichero"
        )

        XCTAssertEqual(payload.apiURL, "https://studio.tailnet-name.ts.net")
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
        XCTAssertNil(decoded.libraryPath)
    }

    func testRemoteClientPairingFieldsNormalizeRemoteHost() throws {
        let apiRoot = URL(string: "https://pairing.example.com/")!
        let code = PairingCodeRecord(
            code: "PAIR-1234",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService(apiRoot: apiRoot).buildQRCodePayload(
            from: code,
            spki: validSPKIPin,
            libraryPath: "/Users/daniel/Archive/Open.fichero"
        )

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let message = try XCTUnwrap(String(bytes: encoder.encode(payload), encoding: .utf8))
        let pairingFields = try RemoteClientPairing.pairingFields(from: message)

        XCTAssertEqual(pairingFields.remoteURL, "https://pairing.example.com")
        XCTAssertEqual(pairingFields.pairCode, "PAIR-1234")
        XCTAssertEqual(pairingFields.spkiPin, validSPKIPin)
        XCTAssertEqual(pairingFields.libraryPath, "/Users/daniel/Archive/Open.fichero")
    }

    func testRemoteClientPairingFieldsAcceptDecodedPayload() throws {
        let apiRoot = URL(string: "https://pairing.example.com/")!
        let code = PairingCodeRecord(
            code: "PAIR-1234",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService(apiRoot: apiRoot).buildQRCodePayload(
            from: code,
            spki: validSPKIPin,
            libraryPath: "  /Users/daniel/Archive/Open.fichero  "
        )

        let pairingFields = try RemoteClientPairing.pairingFields(from: payload)

        XCTAssertEqual(pairingFields.remoteURL, "https://pairing.example.com")
        XCTAssertEqual(pairingFields.pairCode, "PAIR-1234")
        XCTAssertEqual(pairingFields.spkiPin, validSPKIPin)
        XCTAssertEqual(pairingFields.libraryPath, "/Users/daniel/Archive/Open.fichero")
    }

    func testRemoteClientPairingFieldsAcceptInviteLink() throws {
        let apiRoot = URL(string: "https://pairing.example.com/")!
        let code = PairingCodeRecord(
            code: "PAIR-1234",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService(apiRoot: apiRoot).buildQRCodePayload(
            from: code,
            spki: validSPKIPin,
            libraryPath: "/Users/daniel/Archive/Open.fichero"
        )
        let invite = try RemoteClientPairing.inviteLinkString(from: payload)

        let pairingFields = try RemoteClientPairing.pairingFields(fromInviteOrPayload: invite)

        XCTAssertEqual(pairingFields.remoteURL, "https://pairing.example.com")
        XCTAssertEqual(pairingFields.pairCode, "PAIR-1234")
        XCTAssertEqual(pairingFields.spkiPin, validSPKIPin)
        XCTAssertEqual(pairingFields.libraryPath, "/Users/daniel/Archive/Open.fichero")
    }

    func testRemoteClientPairingFieldsRejectMissingLibraryPath() throws {
        let apiRoot = URL(string: "https://pairing.example.com/")!
        let code = PairingCodeRecord(
            code: "PAIR-1234",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService(apiRoot: apiRoot).buildQRCodePayload(from: code, spki: validSPKIPin)

        XCTAssertThrowsError(try RemoteClientPairing.pairingFields(from: payload)) { error in
            XCTAssertEqual(error as? RemoteClientPairingError, .missingLibraryPath)
        }
    }

    func testRemoteClientPairingFieldsRejectMalformedInviteLink() {
        XCTAssertThrowsError(
            try RemoteClientPairing.pairingFields(fromInviteOrPayload: "fichero://pair?payload=not-base64")
        ) { error in
            XCTAssertEqual(error as? RemoteClientPairingError, .invalidInviteLink)
        }
    }

    func testRemoteClientPairingFieldsRejectLocalhostPayloads() throws {
        let apiRoot = URL(string: "https://127.0.0.1:8765/")!
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

    func testPersistPairedHostStoresAdvertisedLibraryPath() throws {
        let result = PairingExchangeResult(apiRoot: attemptedHost, deviceToken: "device-token")

        try RemoteClientPairing.persistPairedHost(
            result,
            expectedSPKIPin: validSPKIPin,
            libraryPath: "  /Users/daniel/Archive/Open.fichero  "
        )

        XCTAssertEqual(UserDefaults.standard.string(forKey: EngineConfig.userDefaultsKey), attemptedHost.absoluteString)
        XCTAssertEqual(RemoteAccessConfig.pairedLibraryPath, "/Users/daniel/Archive/Open.fichero")
        XCTAssertEqual(AuthTokenMiddleware.readRemoteTokenForHost(attemptedHost.absoluteString), "device-token")
        XCTAssertEqual(RemoteCertificatePinning.persistedSPKIPin(hostString: attemptedHost.absoluteString), validSPKIPin)
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
        UserDefaults.standard.set("/Users/daniel/Archive/Open.fichero", forKey: RemoteAccessConfig.pairedLibraryPathKey)

        RemoteClientPairing.rollbackFailedHostSwitch(previousHost: previousHost, attemptedHost: attemptedHost)

        XCTAssertEqual(UserDefaults.standard.string(forKey: EngineConfig.userDefaultsKey), previousHost)
        XCTAssertEqual(RemoteAccessConfig.pairedLibraryPath, "")
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
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: "https://127.0.0.1:8765"))
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

    func testValidatedRemoteURLRejectsLocalHTTPWhenSecureTransportRequired() {
        XCTAssertThrowsError(
            try validatedRemoteURL(
                from: "http://127.0.0.1:8765",
                allowLocalhost: true,
                requireSecureTransportForRemote: true
            )
        ) { error in
            XCTAssertEqual(error as? RemoteURLValidationError, .insecureRemoteTransport)
        }
    }

    func testInsecureRemoteTransportExplainsHttpsRequirement() {
        let message = RemoteURLValidationError.insecureRemoteTransport.errorDescription ?? ""

        XCTAssertTrue(message.contains("HTTPS"))
        XCTAssertFalse(message.contains("Tailscale"))
    }

    func testRemoteAccessTLSMaterialDecodesFromLauncherManifest() throws {
        let json = """
        {
          "bind_host": "pairing.example.com",
          "certificate_path": "/tmp/Fichero Remote Access/server.crt",
          "key_path": "/tmp/Fichero Remote Access/server.key",
          "spki_pin": "c3BraS1waW4="
        }
        """

        let material = try JSONDecoder().decode(
            RemoteAccessTLSMaterial.self,
            from: Data(json.utf8)
        )

        XCTAssertEqual(material.bindHost, "pairing.example.com")
        XCTAssertEqual(material.certificatePath, "/tmp/Fichero Remote Access/server.crt")
        XCTAssertEqual(material.keyPath, "/tmp/Fichero Remote Access/server.key")
        XCTAssertEqual(material.spkiPin, "c3BraS1waW4=")
    }

    func testRemoteAccessLaunchEnvironmentIncludesTLSMaterial() {
        let material = RemoteAccessTLSMaterial(
            bindHost: "pairing.example.com",
            certificatePath: "/tmp/server.crt",
            keyPath: "/tmp/server.key",
            spkiPin: "c3BraS1waW4="
        )
        let publicBaseURL = URL(string: "https://pairing.example.com:9443")!

        let environment = RemoteAccessConfig.launchEnvironment(
            for: publicBaseURL,
            material: material,
            bonjourEnabled: true
        )

        XCTAssertEqual(environment["FICHERO_BIND_HOST"], "pairing.example.com")
        XCTAssertEqual(environment["FICHERO_MULTIUSER"], "1")
        XCTAssertEqual(environment["FICHERO_PUBLIC_BASE_URL"], "https://pairing.example.com:9443")
        XCTAssertEqual(environment["FICHERO_TLS_CERTFILE"], "/tmp/server.crt")
        XCTAssertEqual(environment["FICHERO_TLS_KEYFILE"], "/tmp/server.key")
        XCTAssertEqual(environment["FICHERO_TLS_SPKI_HASH"], "c3BraS1waW4=")
        XCTAssertEqual(environment["FICHERO_ENABLE_BONJOUR"], "1")
        XCTAssertEqual(environment["FICHERO_ALLOW_NON_LOOPBACK_BIND"], "I_UNDERSTAND_SHARED_SECRET_RISK")
    }

    func testRemoteAccessLaunchEnvironmentDisablesMultiuserWhenToggledOff() {
        UserDefaults.standard.set(false, forKey: EngineConfig.multiuserEnabledKey)
        defer { UserDefaults.standard.removeObject(forKey: EngineConfig.multiuserEnabledKey) }

        let material = RemoteAccessTLSMaterial(
            bindHost: "pairing.example.com",
            certificatePath: "/tmp/server.crt",
            keyPath: "/tmp/server.key",
            spkiPin: "c3BraS1waW4="
        )
        let publicBaseURL = URL(string: "https://pairing.example.com:9443")!

        let environment = RemoteAccessConfig.launchEnvironment(
            for: publicBaseURL,
            material: material,
            bonjourEnabled: false
        )

        XCTAssertEqual(environment["FICHERO_MULTIUSER"], "0")
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

    func testValidatedRemoteURLAcceptsHTTPSWhenSecureTransportRequired() throws {
        let url = try validatedRemoteURL(
            from: "https://pairing.example.com",
            allowLocalhost: false,
            requireSecureTransportForRemote: true
        )
        XCTAssertEqual(url.absoluteString, "https://pairing.example.com")
    }
}
// swiftlint:enable type_body_length
