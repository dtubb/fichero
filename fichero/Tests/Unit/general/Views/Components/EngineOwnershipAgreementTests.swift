import FicheroAPIClient
@testable import Fichero
import Foundation
import Testing

/// Two `EngineOwnership` enums, one concept, and nothing forcing them to agree
/// (#4400).
///
/// `EmbeddedBackendService.EngineOwnership` answers "must I kill this on quit?"
/// from strategy + transport + port resolution.
/// `ConnectionPresentation.EngineOwnership` answered "may I offer Restart
/// Engine?" from the STRATEGY ALONE. A `.releaseEmbedded` launch that adopted
/// somebody else's engine therefore reported `.adoptedExternal` to the process
/// layer — `beginStop` correctly refuses to signal it — while telling the
/// popover `.appManaged`, which offered to restart a process the app neither
/// spawned nor may stop.
///
/// The two do NOT collapse into one enum, and these tests pin both the shared
/// input and the one deliberate difference.
struct EngineOwnershipAgreementTests {

    private typealias Presentation = ConnectionPresentation.EngineOwnership

    /// Written out rather than `allCases`: `EngineProvisioningStrategy` is not
    /// `CaseIterable`, and a hand-kept list that goes stale is exactly the
    /// hazard here — so `everyStrategyIsListed` below pins it against the
    /// source.
    private static let allStrategies: [EngineConfig.EngineProvisioningStrategy] =
        [.releaseEmbedded, .debugExternal, .configuredRemote, .iosCompanion, .inert]

    private func presentation(
        _ strategy: EngineConfig.EngineProvisioningStrategy,
        transport: TransportMode? = nil,
        port: EmbeddedBackendService.PortResolution? = nil
    ) -> Presentation {
        Presentation.resolve(
            strategy: strategy,
            transportMode: transport ?? EngineConfig.transportMode(for: strategy),
            portResolution: port
        )
    }

    // MARK: - The bug

    /// The reported defect, stated directly. An adopted engine is not the app's
    /// to restart: `beginStop` returns early on `isExternalBackend`, so the
    /// "restart" would stop nothing and then spawn a second engine against a
    /// socket the first still holds.
    @Test("an adopted engine presents as external, not app-managed")
    func anAdoptedEngineIsNotAppManaged() {
        #expect(presentation(.releaseEmbedded, port: .adoptExisting) == .externalLocal)
    }

    /// The same launch, one input different. Isolating it this way is the point:
    /// the strategy is identical in both, which is exactly why reading the
    /// strategy alone could not tell them apart.
    @Test("only the port resolution separates an adopted launch from an owned one")
    func thePortResolutionIsTheWholeDifference() {
        let owned = presentation(.releaseEmbedded, port: .spawnOurs)
        let adopted = presentation(.releaseEmbedded, port: .adoptExisting)

        #expect(owned == .appManaged)
        #expect(adopted == .externalLocal)
        #expect(owned != adopted)
    }

    // MARK: - The two answers share one table

    /// Whenever the app may offer a restart, the process layer must agree the
    /// engine is ours. A swept assertion rather than a case list, because the
    /// failure mode being guarded is precisely a NEW combination appearing that
    /// nobody thought to enumerate.
    @Test("app-managed never contradicts the process-ownership table")
    func appManagedImpliesOwned() {
        let transports: [TransportMode] = [.https, .uds(path: "/tmp/fichero.sock")]
        let ports: [EmbeddedBackendService.PortResolution?] = [nil, .spawnOurs, .adoptExisting]

        for strategy in Self.allStrategies {
            for transport in transports {
                for port in ports {
                    let shown = presentation(strategy, transport: transport, port: port)
                    guard shown == .appManaged else { continue }

                    let owns = EmbeddedBackendService.engineOwnership(
                        strategy: strategy,
                        transportMode: transport,
                        portResolution: port
                    )
                    #expect(
                        owns == .ownedEmbedded,
                        Comment(rawValue: "\(strategy)/\(transport)/\(String(describing: port)) "
                            + "offers a restart for an engine the process layer will not stop")
                    )
                }
            }
        }
    }

    // MARK: - The one deliberate difference

    /// They must NOT be the same mapping, and this is the case that proves it.
    ///
    /// A Dev Local engine reached over UDS is `.ownedEmbedded` — the app
    /// SIGTERMs it at quit — but `adoptDebugExternalEngine` has no spawn path
    /// at all, so the app can stop that engine and can never start it.
    /// Presenting it as `.appManaged` would offer a restart that stops the
    /// engine and strands the user with no way to bring it back.
    @Test("the Dev Local engine is ours to kill and never ours to start")
    func debugExternalIsOwnedButNotRestartable() {
        let transport = TransportMode.uds(path: "/tmp/fichero.sock")

        let owns = EmbeddedBackendService.engineOwnership(
            strategy: .debugExternal,
            transportMode: transport,
            portResolution: nil
        )

        #expect(owns == .ownedEmbedded)
        #expect(presentation(.debugExternal, transport: transport) == .externalLocal)
    }

    /// Restarting needs BOTH capabilities, so `.appManaged` requires the one
    /// strategy that can spawn. Stated separately from the case above so a
    /// future spawning strategy has to face this assertion rather than
    /// inheriting an answer.
    @Test("only a strategy that can spawn may ever be app-managed")
    func onlyASpawningStrategyIsAppManaged() {
        for strategy in Self.allStrategies where !strategy.spawnsBundledEngine {
            for port in [nil, .spawnOurs, .adoptExisting] as [EmbeddedBackendService.PortResolution?] {
                #expect(presentation(strategy, port: port) != .appManaged)
            }
        }
    }

    /// The hand-kept strategy list, pinned against the source. Without this a
    /// new strategy would be added, the sweeps above would silently stop
    /// covering it, and they would keep passing — the vacuous-guardrail shape
    /// (#4365) this whole cluster keeps running into.
    @Test("every provisioning strategy is covered by the sweeps")
    func everyStrategyIsListed() throws {
        let source = try AppSource.text("Services/EngineConfig+Launch.swift")
        let start = try #require(source.range(of: "enum EngineProvisioningStrategy"))
        // The enum's cases all precede its first computed property; stopping
        // there keeps `case .releaseEmbedded` inside later switches out of the
        // count.
        let end = try #require(
            source.range(of: "var spawnsBundledEngine", range: start.upperBound..<source.endIndex)
        )

        let declared = Set(
            source[start.upperBound..<end.lowerBound]
                .split(separator: "\n")
                .map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { $0.hasPrefix("case ") && !$0.contains(":") && !$0.contains("(") }
                .map { String($0.dropFirst("case ".count)) }
        )

        #expect(declared.count == 5, Comment(rawValue: "found \(declared.sorted())"))
        #expect(
            declared == ["releaseEmbedded", "debugExternal", "configuredRemote", "iosCompanion", "inert"],
            "a provisioning strategy was added or renamed; the sweeps above no longer cover it"
        )
    }

    // MARK: - Nothing else moved

    /// The title-only surfaces keep the answers they had. This change is meant
    /// to correct one wrong answer, not to redraw the connection copy that
    /// #4380 settled and pinned.
    @Test("the strategy-only entry point is unchanged for every strategy")
    func theStrategyOnlyAnswersAreUnchanged() {
        #expect(Presentation.resolve(.releaseEmbedded) == .appManaged)
        #expect(Presentation.resolve(.debugExternal) == .externalLocal)
        #expect(Presentation.resolve(.configuredRemote) == .remote)
        #expect(Presentation.resolve(.iosCompanion) == .remote)
        #expect(Presentation.resolve(.inert) == .externalLocal)
    }

    /// And it is the SAME derivation, not a second copy that happens to agree
    /// today — which is the shape that produced this bug.
    @Test("the strategy-only entry point delegates rather than re-deciding")
    func theStrategyOnlyEntryPointDelegates() {
        for strategy in EngineConfig.EngineProvisioningStrategy.allCases {
            #expect(
                Presentation.resolve(strategy)
                    == presentation(strategy, port: nil)
            )
        }
    }
}
