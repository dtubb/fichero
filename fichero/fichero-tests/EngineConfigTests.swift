import Foundation
import XCTest

@testable import Fichero

final class EngineConfigTests: XCTestCase {
    private func restoreEngineHost(_ value: String?) {
        if let value {
            UserDefaults.standard.set(value, forKey: EngineConfig.userDefaultsKey)
        } else {
            UserDefaults.standard.removeObject(forKey: EngineConfig.userDefaultsKey)
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
        let originalHost = UserDefaults.standard.string(forKey: EngineConfig.userDefaultsKey)
        defer { restoreEngineHost(originalHost) }

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
        let originalHost = UserDefaults.standard.string(forKey: EngineConfig.userDefaultsKey)
        defer { restoreEngineHost(originalHost) }

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
        let originalHost = UserDefaults.standard.string(forKey: EngineConfig.userDefaultsKey)
        defer { restoreEngineHost(originalHost) }

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

    func testExplicitCustomLocalhostStillUsesExternalBackendConnection() {
        let originalHost = UserDefaults.standard.string(forKey: EngineConfig.userDefaultsKey)
        defer { restoreEngineHost(originalHost) }

        let customLocalHost = "http://127.0.0.1:8765"
        let expectedURL = URL(string: customLocalHost)!
        UserDefaults.standard.set(customLocalHost, forKey: EngineConfig.userDefaultsKey)

        XCTAssertEqual(EngineConfig.hostConfiguration(from: customLocalHost), .configured(expectedURL))
        XCTAssertEqual(EngineConfig.host, expectedURL)
        XCTAssertTrue(EngineConfig.engineIsLocal)
        XCTAssertTrue(EngineConfig.usesCustomHost)
        XCTAssertTrue(EngineConfig.requiresExternalBackendConnection)
    }
}
