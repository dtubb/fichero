//
//  EngineProvisioningStrategyTests.swift
//  FicheroTests
//
//  Explicit provisioner decision table (#3109): the launch mode is decided ONCE
//  from explicit inputs — Debug-external / Release-embedded / configured-remote /
//  iOS-companion / inert — instead of scattered #if DEBUG / usesCustomHost /
//  preview conditionals. Includes the #3042 regression: Debug never spawns; a
//  missing external engine fails with the actionable start_backend.sh message,
//  the window renders, the app never terminates.
//

@testable import Fichero
import Foundation
import Testing

@Suite("Engine provisioning strategy (#3109)")
struct EngineProvisioningStrategyTests {

    private typealias Strategy = EngineConfig.EngineProvisioningStrategy

    private func inputs(
        isMacOS: Bool,
        isDebugBuild: Bool = false,
        isInertHost: Bool = false,
        hostRequiresRemoteConnection: Bool = false,
        hasExplicitConfiguredHost: Bool = false
    ) -> EngineConfig.EngineProvisioningInputs {
        .init(
            isMacOS: isMacOS,
            isDebugBuild: isDebugBuild,
            isInertHost: isInertHost,
            hostRequiresRemoteConnection: hostRequiresRemoteConnection,
            hasExplicitConfiguredHost: hasExplicitConfiguredHost
        )
    }

    private func strategy(_ input: EngineConfig.EngineProvisioningInputs) -> Strategy {
        EngineConfig.engineProvisioningStrategy(input)
    }

    // MARK: - Decision table

    @Test("inert host wins over every other input (preview / XCTest / UI-test)")
    func inertAlwaysWins() {
        for isMacOS in [true, false] {
            for isDebug in [true, false] {
                for remote in [true, false] {
                    for configured in [true, false] {
                        let result = strategy(inputs(
                            isMacOS: isMacOS,
                            isDebugBuild: isDebug,
                            isInertHost: true,
                            hostRequiresRemoteConnection: remote,
                            hasExplicitConfiguredHost: configured
                        ))
                        #expect(result == .inert)
                    }
                }
            }
        }
    }

    @Test("macOS Debug, no configured host → debugExternal (never spawns)")
    func macDebugIsExternal() {
        let result = strategy(inputs(isMacOS: true, isDebugBuild: true))
        #expect(result == .debugExternal)
        #expect(result.spawnsBundledEngine == false)
        #expect(result.connectsToRemoteHost == false)
    }

    @Test("macOS Release, no configured host → releaseEmbedded (the only spawner)")
    func macReleaseIsEmbedded() {
        let result = strategy(inputs(isMacOS: true, isDebugBuild: false))
        #expect(result == .releaseEmbedded)
        #expect(result.spawnsBundledEngine == true)
        #expect(result.connectsToRemoteHost == false)
    }

    @Test("macOS with a configured/remote host → configuredRemote, Debug or Release")
    func macConfiguredHostIsRemote() {
        for isDebug in [true, false] {
            let result = strategy(inputs(
                isMacOS: true,
                isDebugBuild: isDebug,
                hostRequiresRemoteConnection: true,
                hasExplicitConfiguredHost: true
            ))
            #expect(result == .configuredRemote)
            #expect(result.spawnsBundledEngine == false)
            #expect(result.connectsToRemoteHost == true)
        }
    }

    @Test("macOS with a MALFORMED host still avoids a local spawn → configuredRemote")
    func macInvalidHostIsRemote() {
        // requiresExternalBackendConnection is true for invalid hosts too, so a
        // typo'd host surfaces the error rather than silently spawning locally.
        let result = strategy(inputs(
            isMacOS: true,
            hostRequiresRemoteConnection: true,
            hasExplicitConfiguredHost: false
        ))
        #expect(result == .configuredRemote)
    }

    @Test("iOS with a valid Settings host → configuredRemote")
    func iosConfiguredHostIsRemote() {
        let result = strategy(inputs(
            isMacOS: false,
            hostRequiresRemoteConnection: true,
            hasExplicitConfiguredHost: true
        ))
        #expect(result == .configuredRemote)
    }

    @Test("iOS unpaired / no valid host → iosCompanion (never a local engine)")
    func iosUnpairedIsCompanion() {
        // Blank/invalid host on iOS: requiresExternalBackendConnection is true
        // but hasConfiguredHost is false → the paired companion / first-run setup.
        for remote in [true, false] {
            let result = strategy(inputs(
                isMacOS: false,
                hostRequiresRemoteConnection: remote,
                hasExplicitConfiguredHost: false
            ))
            #expect(result == .iosCompanion)
            #expect(result.spawnsBundledEngine == false)
        }
    }

    // MARK: - #3042 regression

    @Test("#3042: Debug adopts external and never spawns the bundled engine")
    func debugNeverSpawns() {
        let result = strategy(inputs(isMacOS: true, isDebugBuild: true))
        #expect(result == .debugExternal)
        #expect(result.spawnsBundledEngine == false)
        // Only releaseEmbedded spawns — nothing else in the table does.
        for nonSpawning in [Strategy.inert, .configuredRemote, .iosCompanion, .debugExternal] {
            #expect(nonSpawning.spawnsBundledEngine == false)
        }
        #expect(Strategy.releaseEmbedded.spawnsBundledEngine == true)
    }

    @Test("#3042: the Debug 'engine not bundled' error carries the actionable start_backend.sh message")
    func debugErrorIsActionable() {
        // adoptDebugExternalEngine throws backendAppNotFound when nothing is on
        // :8765; in a Debug build its message points at start_backend.sh so the
        // rendered diagnosis is actionable (not a blank window).
        let message = BackendError.backendAppNotFound.errorDescription ?? ""
        #if DEBUG
        #expect(message.contains("start_backend.sh"))
        #else
        #expect(message.contains("briefcase"))
        #endif
    }

    // MARK: - iOS companion never probes localhost (#2465)

    @Test("iosCompanion produces no localhost candidate")
    func iosCompanionHasNoLocalhostCandidate() {
        // Unpaired: no candidates at all (localhost is never probed on iOS).
        let none = EngineConfig.orderedConnectionCandidates(savedHostString: nil, isMacOS: false)
        #expect(none.isEmpty)

        // Paired to a real remote: that host only, never a loopback fallback.
        let paired = EngineConfig.orderedConnectionCandidates(
            savedHostString: "https://studio.local:8765",
            isMacOS: false
        )
        #expect(paired.allSatisfy { url in
            let host = url.host?.lowercased() ?? ""
            return host != "localhost" && !host.hasPrefix("127.") && host != "::1"
        })
    }
}
