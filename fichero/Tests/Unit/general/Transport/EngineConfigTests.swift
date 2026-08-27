import FicheroAPIClient
import Foundation
import XCTest

@testable import Fichero

final class EngineConfigTests: XCTestCase {

    // Writes go to a throwaway suite, never the developer's real app domain
    // (#4221). The previous snapshot-and-restore is gone deliberately: it only
    // worked when teardown ran, and a killed process skips teardown.
    override func setUp() {
        super.setUp()
        TestDefaults.reset()
    }

    override func tearDown() {
        RemoteCertificatePinning.clearAdvertisedSPKIPin(hostString: "https://fichero.local:9443")
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: "https://fichero.local:9443")
        TestDefaults.uninstall()
        super.tearDown()
    }

    private func restoreEngineHost(_ value: String?) {
        if let value {
            EngineConfig.defaults.set(value, forKey: EngineConfig.userDefaultsKey)
        } else {
            EngineConfig.defaults.removeObject(forKey: EngineConfig.userDefaultsKey)
        }
    }

    private func restoreRemoteAccessState(enabled: Bool?, publicBaseURL: String?) {
        if let enabled {
            EngineConfig.defaults.set(enabled, forKey: RemoteAccessConfig.hostingEnabledKey)
        } else {
            EngineConfig.defaults.removeObject(forKey: RemoteAccessConfig.hostingEnabledKey)
        }
        if let publicBaseURL {
            EngineConfig.defaults.set(publicBaseURL, forKey: RemoteAccessConfig.publicBaseURLKey)
        } else {
            EngineConfig.defaults.removeObject(forKey: RemoteAccessConfig.publicBaseURLKey)
        }
    }

    func testBlankHostPolicyDependsOnEmbeddedLocalAllowance() {
        XCTAssertEqual(
            EngineConfig.hostConfiguration(from: nil, allowsImplicitEmbeddedLocalDefault: true),
            .embeddedLocal
        )
        XCTAssertEqual(
            EngineConfig.hostConfiguration(from: "   ", allowsImplicitEmbeddedLocalDefault: true),
            .embeddedLocal
        )
        XCTAssertEqual(
            EngineConfig.hostConfiguration(from: nil, allowsImplicitEmbeddedLocalDefault: false),
            .invalid("")
        )
        XCTAssertEqual(
            EngineConfig.hostConfiguration(from: "   ", allowsImplicitEmbeddedLocalDefault: false),
            .invalid("")
        )
    }

    func testBlankHostUsesCurrentPlatformDefaultPolicy() {
        EngineConfig.defaults.set("   ", forKey: EngineConfig.userDefaultsKey)

        #if os(macOS)
        XCTAssertEqual(EngineConfig.hostConfiguration(from: nil), .embeddedLocal)
        XCTAssertEqual(EngineConfig.hostConfiguration(from: "   "), .embeddedLocal)
        XCTAssertEqual(EngineConfig.hostString, EngineConfig.defaultHostString)
        XCTAssertEqual(EngineConfig.host.absoluteString, EngineConfig.defaultHostString)
        XCTAssertFalse(EngineConfig.usesCustomHost)
        XCTAssertTrue(EngineConfig.engineIsLocal)
        XCTAssertFalse(EngineConfig.requiresExternalBackendConnection)
        #else
        XCTAssertEqual(EngineConfig.hostConfiguration(from: nil), .invalid(""))
        XCTAssertEqual(EngineConfig.hostConfiguration(from: "   "), .invalid(""))
        XCTAssertEqual(EngineConfig.hostString, "")
        XCTAssertNotEqual(EngineConfig.host.absoluteString, EngineConfig.defaultHostString)
        XCTAssertTrue(EngineConfig.usesCustomHost)
        XCTAssertFalse(EngineConfig.engineIsLocal)
        XCTAssertTrue(EngineConfig.requiresExternalBackendConnection)
        #endif
    }

    func testValidRemoteHostIsPreserved() {
        let remoteHost = "https://host.tailnet.example/"
        let expectedURL = URL(string: "https://host.tailnet.example")!
        EngineConfig.defaults.set(remoteHost, forKey: EngineConfig.userDefaultsKey)

        XCTAssertEqual(EngineConfig.hostConfiguration(from: remoteHost), .configured(expectedURL))
        XCTAssertEqual(EngineConfig.hostString, expectedURL.absoluteString)
        XCTAssertEqual(EngineConfig.host, expectedURL)
        XCTAssertTrue(EngineConfig.usesCustomHost)
        XCTAssertFalse(EngineConfig.engineIsLocal)
        XCTAssertTrue(EngineConfig.requiresExternalBackendConnection)
    }

    func testMalformedNonEmptyHostDoesNotBecomeLocalhost() {
        let malformedHost = "https://remote host/"
        EngineConfig.defaults.set(malformedHost, forKey: EngineConfig.userDefaultsKey)

        XCTAssertEqual(EngineConfig.hostConfiguration(from: malformedHost), .invalid("https://remote host"))
        XCTAssertEqual(
            EngineConfig.hostConfiguration(from: malformedHost, allowsImplicitEmbeddedLocalDefault: true),
            .invalid("https://remote host")
        )
        XCTAssertEqual(
            EngineConfig.hostConfiguration(from: malformedHost, allowsImplicitEmbeddedLocalDefault: false),
            .invalid("https://remote host")
        )
        XCTAssertEqual(EngineConfig.hostString, "https://remote host")
        XCTAssertNotEqual(EngineConfig.host.absoluteString, EngineConfig.defaultHostString)
        XCTAssertFalse(EngineConfig.engineIsLocal)
        XCTAssertTrue(EngineConfig.usesCustomHost)
        XCTAssertTrue(EngineConfig.requiresExternalBackendConnection)
    }

    func testExplicitHTTPSLocalhostStillUsesExternalBackendConnection() {
        let customLocalHost = "https://127.0.0.1:8765"
        let expectedURL = URL(string: customLocalHost)!
        EngineConfig.defaults.set(customLocalHost, forKey: EngineConfig.userDefaultsKey)

        XCTAssertEqual(EngineConfig.hostConfiguration(from: customLocalHost), .configured(expectedURL))
        XCTAssertEqual(EngineConfig.host, expectedURL)
        XCTAssertTrue(EngineConfig.engineIsLocal)
        XCTAssertTrue(EngineConfig.usesCustomHost)
        XCTAssertTrue(EngineConfig.requiresExternalBackendConnection)
    }

    func testHTTPHostIsInvalid() {
        XCTAssertEqual(
            EngineConfig.hostConfiguration(from: "http://127.0.0.1:8765"),
            .invalid("http://127.0.0.1:8765")
        )
        XCTAssertEqual(
            EngineConfig.hostConfiguration(from: "http://host.tailnet.example"),
            .invalid("http://host.tailnet.example")
        )
    }

    func testValidatedHostedRemoteURLAcceptsLiteralIPAndLocalHost() throws {
        let ipURL = try validatedHostedRemoteURL(from: "https://192.168.1.42:9443")
        XCTAssertEqual(ipURL.absoluteString, "https://192.168.1.42:9443")

        let localURL = try validatedHostedRemoteURL(from: "https://fichero.local:9443")
        XCTAssertEqual(localURL.absoluteString, "https://fichero.local:9443")
    }

    func testValidatedHostedRemoteURLRejectsArbitraryDNSHostnames() {
        XCTAssertThrowsError(
            try validatedHostedRemoteURL(from: "https://pairing.example.com:9443")
        ) { error in
            XCTAssertEqual(error as? RemoteURLValidationError, .hostPolicyNotAllowed)
        }
    }

    func testHostedBackendSPKIPinFallsBackToPersistedPin() throws {
        let hostedURL = "https://fichero.local:9443"
        EngineConfig.defaults.set(hostedURL, forKey: RemoteAccessConfig.publicBaseURLKey)
        let fallbackPin = Data(repeating: 0xAB, count: 32).base64EncodedString()
        try RemoteCertificatePinning.persistSPKIPin("sha256/\(fallbackPin)", hostString: hostedURL)

        XCTAssertEqual(RemoteAccessConfig.hostedBackendSPKIPin(hostString: hostedURL), "sha256/\(fallbackPin)")
        XCTAssertEqual(RemoteAccessConfig.advertisedSPKIPin, "sha256/\(fallbackPin)")
    }

    func testHostedRemoteAccessURLDoesNotOverrideActiveEngineHost() {
        let originalHost = EngineConfig.defaults.string(forKey: EngineConfig.userDefaultsKey)
        let originalRemoteEnabled = EngineConfig.defaults.object(forKey: RemoteAccessConfig.hostingEnabledKey) as? Bool
        let originalPublicBaseURL = EngineConfig.defaults.string(forKey: RemoteAccessConfig.publicBaseURLKey)
        defer {
            restoreEngineHost(originalHost)
            restoreRemoteAccessState(enabled: originalRemoteEnabled, publicBaseURL: originalPublicBaseURL)
        }

        EngineConfig.defaults.set(true, forKey: RemoteAccessConfig.hostingEnabledKey)
        EngineConfig.defaults.set("https://192.168.1.42:9443", forKey: RemoteAccessConfig.publicBaseURLKey)

        XCTAssertEqual(EngineConfig.host.absoluteString, EngineConfig.defaultHostString)
        XCTAssertEqual(EngineConfig.apiBaseURL.absoluteString, EngineConfig.defaultHostString + "/api")
    }

    // MARK: - Connection candidate ordering (#2465)

    func testIOSConnectionCandidatesPreferSavedRemoteAndSkipLocalhost() {
        let remote = "https://host.tailnet.example:9443/"
        let expected = URL(string: "https://host.tailnet.example:9443")!

        let candidates = EngineConfig.orderedConnectionCandidates(
            savedHostString: remote,
            isMacOS: false
        )

        XCTAssertEqual(candidates, [expected])
        // localhost must never be probed on iOS — it has no engine.
        XCTAssertFalse(candidates.contains { $0.host == "127.0.0.1" || $0.host == "localhost" })
    }

    func testIOSWithNoSavedHostHasNoLocalhostFallback() {
        XCTAssertTrue(
            EngineConfig.orderedConnectionCandidates(savedHostString: nil, isMacOS: false).isEmpty
        )
        XCTAssertTrue(
            EngineConfig.orderedConnectionCandidates(savedHostString: "   ", isMacOS: false).isEmpty
        )
    }

    func testMacOSConnectionCandidatesPreferLocalhostFirst() {
        let localhost = URL(string: EngineConfig.defaultHostString)!

        // No saved host → localhost only.
        XCTAssertEqual(
            EngineConfig.orderedConnectionCandidates(savedHostString: nil, isMacOS: true),
            [localhost]
        )

        // Saved remote → localhost first, remote as fallback.
        let remote = "https://host.tailnet.example:9443/"
        let expectedRemote = URL(string: "https://host.tailnet.example:9443")!
        XCTAssertEqual(
            EngineConfig.orderedConnectionCandidates(savedHostString: remote, isMacOS: true),
            [localhost, expectedRemote]
        )
    }

    func testMacOSDoesNotDuplicateLocalhostCandidate() {
        let localhost = URL(string: EngineConfig.defaultHostString)!
        let candidates = EngineConfig.orderedConnectionCandidates(
            savedHostString: "https://127.0.0.1:8765",
            isMacOS: true
        )
        XCTAssertEqual(candidates, [localhost])
    }

    // Payload minting takes the ADVERTISED root directly and constructs no
    // client — it describes where a phone should connect, and sends nothing
    // (#4224).
    @MainActor
    func testPairingServiceBuildsQRCodePayloadFromAdvertisedRoot() {
        let apiRoot = URL(string: "https://192.168.1.42:9443/")!
        let code = PairingCodeRecord(code: "ABC123", expiresAt: Date(timeIntervalSince1970: 0))

        let payload = PairingService.buildQRCodePayload(
            apiRoot: apiRoot,
            from: code,
            spki: "sha256/abc=",
            libraryPath: "/path/to/lib"
        )

        XCTAssertEqual(payload.apiURL, "https://192.168.1.42:9443")
        XCTAssertEqual(payload.pairCode, "ABC123")
        XCTAssertEqual(payload.spki, "sha256/abc=")
        XCTAssertEqual(payload.libraryPath, "/path/to/lib")
        XCTAssertEqual(payload.version, 1)
    }

    // MARK: - Mac launch connection mode (#2381)

    func testNormalInteractiveLaunchUsesEmbeddedLocal() {
        // No Option held → normal launch starts the embedded local engine.
        XCTAssertEqual(
            EngineConfig.macLaunchConnectionMode(
                optionKeyHeld: false,
                isInteractiveLaunch: true
            ),
            .embeddedLocal
        )
    }

    func testOptionHeldInteractiveLaunchShowsRemoteChooser() {
        // Option held on a real launch → the remote-client connection chooser.
        XCTAssertEqual(
            EngineConfig.macLaunchConnectionMode(
                optionKeyHeld: true,
                isInteractiveLaunch: true
            ),
            .remoteConnectionChooser
        )
    }

    func testOptionHeldNonInteractiveLaunchNeverShowsChooser() {
        // Previews / UI-tests / XCTest hosts drive the app non-interactively and
        // must never pop the chooser, even if Option happens to be held.
        XCTAssertEqual(
            EngineConfig.macLaunchConnectionMode(
                optionKeyHeld: true,
                isInteractiveLaunch: false
            ),
            .embeddedLocal
        )
    }

    func testNonInteractiveLaunchWithoutOptionUsesEmbeddedLocal() {
        XCTAssertEqual(
            EngineConfig.macLaunchConnectionMode(
                optionKeyHeld: false,
                isInteractiveLaunch: false
            ),
            .embeddedLocal
        )
    }
}
