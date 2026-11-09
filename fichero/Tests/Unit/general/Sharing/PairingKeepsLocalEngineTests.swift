//
//  PairingKeepsLocalEngineTests.swift
//  FicheroTests
//
//  #6418: pairing with another Mac must not make it THIS Mac's engine. It did, and the next launch dialled that Mac instead of
//  starting its own engine, so a sleeping host meant a dead window.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
struct PairingKeepsLocalEngineTests {
    private let host = URL(string: "https://paired-\(UUID().uuidString.lowercased()).example:8765")!

    private func scratch() -> UserDefaults {
        let suite = "PairingKeepsLocalEngineTests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defaults.removePersistentDomain(forName: suite)
        return defaults
    }

    @Test func aMacThatOnlyPairsKeepsItsOwnEngineAtTheNextLaunch() throws {
        let saved = EngineConfig.defaults.string(forKey: EngineConfig.userDefaultsKey)
        EngineConfig.defaults.removeObject(forKey: EngineConfig.userDefaultsKey)
        defer {
            AuthTokenMiddleware.clearRemoteToken(hostString: host.absoluteString)
            RemoteCertificatePinning.clearPersistedSPKIPin(hostString: host.absoluteString)
            if let saved { EngineConfig.defaults.set(saved, forKey: EngineConfig.userDefaultsKey) }
        }
        let expiry = Date(timeIntervalSince1970: 2_000_000_000)
        let result = PairingExchangeResult(apiRoot: host, deviceToken: "device-token", expiresAt: expiry)
        try RemoteClientPairing.persistPairedHost(
            result, expectedSPKIPin: Data("spki".utf8).base64EncodedString(), libraryPath: "/A", makesAppHost: false)

        #expect(EngineConfig.defaults.string(forKey: EngineConfig.userDefaultsKey) == nil)
        #expect(AuthTokenMiddleware.readRemoteTokenForHost(host.absoluteString) == "device-token")  // still able to dial it per library
        let inputs = EngineConfig.EngineProvisioningInputs(
            isMacOS: true, isDebugBuild: false, isInertHost: false,
            hostRequiresRemoteConnection: EngineConfig.requiresExternalBackendConnection, hasExplicitConfiguredHost: false)
        #expect(EngineConfig.engineProvisioningStrategy(inputs) == .releaseEmbedded)
    }

    @Test func aPairedMacStoredWithoutBeingChosenIsDroppedAtLaunch() {
        let defaults = scratch()
        defaults.set(host.absoluteString, forKey: EngineConfig.userDefaultsKey)
        #expect(EngineConfig.dropUnchosenPairedHost(paired: [host.absoluteString], defaults: defaults, isMacOS: true))
        #expect(defaults.string(forKey: EngineConfig.userDefaultsKey) == nil)
    }

    @Test func aPairedMacTheMacWasSwitchedToStays() {
        let defaults = scratch()
        defaults.set(host.absoluteString, forKey: EngineConfig.userDefaultsKey)
        defaults.set(host.absoluteString, forKey: EngineConfig.wholeMacHostKey)
        #expect(!EngineConfig.dropUnchosenPairedHost(paired: [host.absoluteString], defaults: defaults, isMacOS: true))
        #expect(defaults.string(forKey: EngineConfig.userDefaultsKey) == host.absoluteString)
    }

    @Test func aHostTypedInAdvancedSettingsIsLeftAlone() {
        let defaults = scratch()
        defaults.set(host.absoluteString, forKey: EngineConfig.userDefaultsKey)
        #expect(!EngineConfig.dropUnchosenPairedHost(paired: [], defaults: defaults, isMacOS: true))
        #expect(!EngineConfig.dropUnchosenPairedHost(paired: [host.absoluteString], defaults: defaults, isMacOS: false))
        #expect(defaults.string(forKey: EngineConfig.userDefaultsKey) == host.absoluteString)
    }
}
