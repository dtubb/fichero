import Foundation
import XCTest

@testable import Fichero

final class EngineConfigTests: XCTestCase {
    private var originalHost: String?
    private var originalRemoteEnabled: Bool?
    private var originalPublicBaseURL: String?

    override func setUp() {
        super.setUp()
        originalHost = UserDefaults.standard.string(forKey: EngineConfig.userDefaultsKey)
        originalRemoteEnabled = UserDefaults.standard.object(forKey: RemoteAccessConfig.hostingEnabledKey) as? Bool
        originalPublicBaseURL = UserDefaults.standard.string(forKey: RemoteAccessConfig.publicBaseURLKey)
        restoreEngineHost(nil)
        restoreRemoteAccessState(enabled: nil, publicBaseURL: nil)
    }

    override func tearDown() {
        restoreEngineHost(originalHost)
        restoreRemoteAccessState(enabled: originalRemoteEnabled, publicBaseURL: originalPublicBaseURL)
        originalHost = nil
        originalRemoteEnabled = nil
        originalPublicBaseURL = nil
        super.tearDown()
    }

    private func restoreEngineHost(_ value: String?) {
        if let value {
            UserDefaults.standard.set(value, forKey: EngineConfig.userDefaultsKey)
        } else {
            UserDefaults.standard.removeObject(forKey: EngineConfig.userDefaultsKey)
        }
    }

    private func restoreRemoteAccessState(enabled: Bool?, publicBaseURL: String?) {
        if let enabled {
            UserDefaults.standard.set(enabled, forKey: RemoteAccessConfig.hostingEnabledKey)
        } else {
            UserDefaults.standard.removeObject(forKey: RemoteAccessConfig.hostingEnabledKey)
        }
        if let publicBaseURL {
            UserDefaults.standard.set(publicBaseURL, forKey: RemoteAccessConfig.publicBaseURLKey)
        } else {
            UserDefaults.standard.removeObject(forKey: RemoteAccessConfig.publicBaseURLKey)
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
        UserDefaults.standard.set("   ", forKey: EngineConfig.userDefaultsKey)

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
        UserDefaults.standard.set(remoteHost, forKey: EngineConfig.userDefaultsKey)

        XCTAssertEqual(EngineConfig.hostConfiguration(from: remoteHost), .configured(expectedURL))
        XCTAssertEqual(EngineConfig.hostString, expectedURL.absoluteString)
        XCTAssertEqual(EngineConfig.host, expectedURL)
        XCTAssertTrue(EngineConfig.usesCustomHost)
        XCTAssertFalse(EngineConfig.engineIsLocal)
        XCTAssertTrue(EngineConfig.requiresExternalBackendConnection)
    }

    func testMalformedNonEmptyHostDoesNotBecomeLocalhost() {
        let malformedHost = "https://remote host/"
        UserDefaults.standard.set(malformedHost, forKey: EngineConfig.userDefaultsKey)

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
        UserDefaults.standard.set(customLocalHost, forKey: EngineConfig.userDefaultsKey)

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

    func testHostedRemoteAccessURLOverridesActiveEngineHost() {
        let originalHost = UserDefaults.standard.string(forKey: EngineConfig.userDefaultsKey)
        let originalRemoteEnabled = UserDefaults.standard.object(forKey: RemoteAccessConfig.hostingEnabledKey) as? Bool
        let originalPublicBaseURL = UserDefaults.standard.string(forKey: RemoteAccessConfig.publicBaseURLKey)
        defer {
            restoreEngineHost(originalHost)
            restoreRemoteAccessState(enabled: originalRemoteEnabled, publicBaseURL: originalPublicBaseURL)
        }

        UserDefaults.standard.set(true, forKey: RemoteAccessConfig.hostingEnabledKey)
        UserDefaults.standard.set("https://192.168.1.42:9443", forKey: RemoteAccessConfig.publicBaseURLKey)

        XCTAssertEqual(EngineConfig.host.absoluteString, "https://192.168.1.42:9443")
        XCTAssertEqual(EngineConfig.apiBaseURL.absoluteString, "https://192.168.1.42:9443/api")
    }

    @MainActor
    func testPairingServiceBuildsQRCodePayloadFromClientBaseURL() {
        let apiRoot = URL(string: "https://192.168.1.42:9443/")!
        let service = PairingService(apiRoot: apiRoot)
        let code = PairingCodeRecord(code: "ABC123", expiresAt: Date(timeIntervalSince1970: 0))

        let payload = service.buildQRCodePayload(
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
}
