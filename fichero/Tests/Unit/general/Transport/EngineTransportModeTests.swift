//
//  EngineTransportModeTests.swift
//  FicheroTests
//
//  Transport selection for the embedded engine: the app client's transport is
//  derived ONCE from the provisioning strategy. Only `.releaseEmbedded` (the
//  bundled-engine spawn) binds an AF_UNIX socket, so only it dials UDS; every
//  other strategy keeps the existing HTTPS path unchanged. Pairs with the
//  engine's Lane E, which binds UDS-only when FICHERO_UDS_PATH is set.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// spec: transport-http-uds — the transport-selection precedence table
/// (`localDebugTransportOverride`) and the strategy→mode mapping.
@Suite("Engine transport mode", .tags(.transport))
struct EngineTransportModeTests {

    private typealias Strategy = EngineConfig.EngineProvisioningStrategy

    @Test("releaseEmbedded dials UDS at the shared socket path")
    func releaseEmbeddedIsUDS() {
        let mode = EngineConfig.transportMode(for: .releaseEmbedded)
        #expect(mode == .uds(path: EngineConfig.udsSocketPath))
    }

    @Test("debugExternal stays HTTPS")
    func debugExternalIsHTTPS() {
        #expect(EngineConfig.transportMode(for: .debugExternal) == .https)
    }

    @Test("configuredRemote stays HTTPS")
    func configuredRemoteIsHTTPS() {
        #expect(EngineConfig.transportMode(for: .configuredRemote) == .https)
    }

    @Test("iosCompanion stays HTTPS")
    func iosCompanionIsHTTPS() {
        #expect(EngineConfig.transportMode(for: .iosCompanion) == .https)
    }

    @Test("inert stays HTTPS")
    func inertIsHTTPS() {
        #expect(EngineConfig.transportMode(for: .inert) == .https)
    }

    @Test("UI-test UDS override wins over a saved remote host")
    func uiTestUDSOverrideWinsOverRemoteHost() {
        let mode = EngineConfig.localDebugTransportOverride(
            environment: ["FICHERO_FORCE_UDS_PATH": "/tmp/test.sock"],
            hostRequiresRemoteConnection: true,
            uiTesting: true
        )

        #expect(mode == .uds(path: "/tmp/test.sock"))
    }

    @Test("FICHERO_FORCE_UDS_PATH dials UDS for a local engine (not UI testing)")
    func forceUDSPathDialsUDSLocally() {
        let mode = EngineConfig.localDebugTransportOverride(
            environment: ["FICHERO_FORCE_UDS_PATH": "/tmp/local.sock"],
            hostRequiresRemoteConnection: false,
            uiTesting: false
        )
        #expect(mode == .uds(path: "/tmp/local.sock"))
    }

    @Test("FICHERO_FORCE_UDS=1 dials the app-computed socket path")
    func forceUDSFlagUsesComputedPath() {
        let mode = EngineConfig.localDebugTransportOverride(
            environment: ["FICHERO_FORCE_UDS": "1"],
            hostRequiresRemoteConnection: false,
            uiTesting: false
        )
        #expect(mode == .uds(path: EngineConfig.udsSocketPath))
    }

    @Test("in-memory wins when both in-memory and UDS overrides are set")
    func inMemoryWinsOverUDS() {
        let mode = EngineConfig.localDebugTransportOverride(
            environment: [
                "FICHERO_FORCE_INMEMORY": "1",
                "FICHERO_FORCE_UDS_PATH": "/tmp/ignored.sock",
            ],
            hostRequiresRemoteConnection: false,
            uiTesting: false
        )
        #expect(mode == .inMemory)
    }

    @Test("a saved remote host is not redirected to a local override outside UI testing")
    func remoteHostKeepsHTTPSOutsideUITesting() {
        let mode = EngineConfig.localDebugTransportOverride(
            environment: ["FICHERO_FORCE_UDS_PATH": "/tmp/local.sock"],
            hostRequiresRemoteConnection: true,
            uiTesting: false
        )
        #expect(mode == nil)  // nil => fall through to the strategy's transport (HTTPS)
    }

    @Test("no override env returns nil (default path stays HTTPS)")
    func noOverrideReturnsNil() {
        let mode = EngineConfig.localDebugTransportOverride(
            environment: [:],
            hostRequiresRemoteConnection: false,
            uiTesting: false
        )
        #expect(mode == nil)
    }

    @Test("socket path stays well under the ~104-byte sun_path limit")
    func socketPathIsShortEnough() {
        // AF_UNIX `sun_path` is ~104 bytes; a path at/over that fails to bind.
        #expect(EngineConfig.udsSocketPath.utf8.count < 104)
        // The socket moved to NSTemporaryDirectory()/fichero.sock: the old
        // Application Support "/Fichero/engine.sock" overflowed sun_path
        // inside the App Store container (see udsSocketPath's doc comment).
        #expect(EngineConfig.udsSocketPath.hasSuffix("/fichero.sock"))
    }
}
