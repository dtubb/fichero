@testable import Fichero
import Foundation
import Testing

// Pairing built its own HTTPS client from a base URL instead of using the
// transport the app resolved at launch (#4224). Every other call went over the
// engine's UDS socket and worked; pairing alone dialled
// `https://127.0.0.1:8765`, where nothing listens in a Release build, so
// sharing hung on "Preparing the security certificate" forever.
//
// The reason it survived: `.debugExternal` — the Debug strategy — resolves to
// `.https`, so pairing worked in the one configuration developers use and
// failed in every configuration users get.
@Suite("Pairing follows the app's transport (#4224)")
struct PairingTransportTests {

    // The defect in one assertion: the shipping strategy dials a socket, so
    // anything hardcoding HTTPS is talking to a port nothing is bound to.
    @Test("every Release macOS build resolves to UDS, not HTTPS")
    func releaseEmbeddedUsesUDS() {
        let transport = EngineConfig.transportMode(for: .releaseEmbedded)
        guard case .uds = transport else {
            Issue.record("releaseEmbedded must dial the socket it binds, got \(transport)")
            return
        }
    }

    // Why nobody noticed: the development configuration is not the shipping one.
    @Test("Debug resolves to HTTPS — the configuration where the bug was invisible")
    func debugExternalUsesHTTPS() {
        #expect(EngineConfig.transportMode(for: .debugExternal) == .https)
    }

    // A phone has no socket to dial and no loopback to the Mac, so the remote
    // strategies must stay HTTPS regardless of what the local app resolved.
    @Test("remote and iOS strategies stay HTTPS")
    func remoteStrategiesStayHTTPS() {
        #expect(EngineConfig.transportMode(for: .configuredRemote) == .https)
        #expect(EngineConfig.transportMode(for: .iosCompanion) == .https)
        #expect(EngineConfig.transportMode(for: .inert) == .https)
    }

    // The source-level half: `PairingService`'s plain init must not construct a
    // client from a URL alone. This asserts the call passes a transport — it
    // cannot prove the transport is CORRECT at runtime, which needs a Release
    // build with a live socket.
    @Test("the pairing client is constructed with a transport, not just a URL")
    func pairingPassesTransport() throws {
        let source = try String(
            contentsOf: try AppSource.root().appendingPathComponent("Services/PairingTypes.swift"),
            encoding: .utf8
        )
        #expect(
            source.contains("FicheroClient(baseURL: apiRoot, transportMode:"),
            "pairing must use the app's resolved transport, not a bare base URL"
        )
    }

    // The pinned init is for a DEVICE dialling a remote Mac: HTTPS with
    // certificate pinning is correct there, and a UDS path does not exist on a
    // phone. It must never follow the local app's transport.
    @Test("the pinned init stays HTTPS and is not routed through the app's transport")
    func pinnedInitStaysHTTPS() throws {
        let source = try String(
            contentsOf: try AppSource.root().appendingPathComponent("Services/PairingTypes.swift"),
            encoding: .utf8
        )
        #expect(
            source.contains("FicheroClient(baseURL: apiRoot, expectedSPKIPin: expectedSPKIPin)"),
            "the pinned path must keep its own construction — pinning is an HTTPS concern"
        )
    }
}
