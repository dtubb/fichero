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

@Suite("Engine transport mode")
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

    @Test("socket path stays well under the ~104-byte sun_path limit")
    func socketPathIsShortEnough() {
        // AF_UNIX `sun_path` is ~104 bytes; a path at/over that fails to bind.
        #expect(EngineConfig.udsSocketPath.utf8.count < 104)
        #expect(EngineConfig.udsSocketPath.hasSuffix("/Fichero/engine.sock"))
    }
}
