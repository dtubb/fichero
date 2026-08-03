import FicheroAPIClient
import Foundation

// Two enums, one concept, nothing forcing them to agree (#4400).
//
// `EmbeddedBackendService.EngineOwnership` answers "must I kill this on quit?"
// and consults strategy + transport + port resolution.
// `ConnectionPresentation.EngineOwnership` answers "may I offer Restart
// Engine?" and consulted the STRATEGY ALONE. So a `.releaseEmbedded` launch
// that adopted somebody else's engine reported `.adoptedExternal` to the
// process layer — `beginStop` correctly refuses to signal it — while still
// reporting `.appManaged` to the popover, which then offered to restart a
// process the app neither spawned nor may stop.
//
// The two CANNOT collapse into one enum: `.remote` names another machine and
// has no process-lifecycle meaning, and the questions genuinely differ (see
// `debugExternalIsOwnedButNotRestartable` in the tests — the Dev Local engine
// is ours to kill and never ours to start). What they must share is the
// ownership TABLE, so there is one place where "is this process ours" is
// decided.

extension ConnectionPresentation.EngineOwnership {

    /// Ownership from every input that bears on it (#4400).
    ///
    /// Restarting takes two capabilities, and the app needs BOTH:
    ///   * it must be able to START the engine — only `spawnsBundledEngine`;
    ///   * it must be able to STOP it — the shared process-ownership table.
    ///
    /// Missing either one means the honest answer is `.externalLocal`: the app
    /// can try to connect again, and that is all.
    static func resolve(
        strategy: EngineConfig.EngineProvisioningStrategy,
        transportMode: TransportMode,
        portResolution: EmbeddedBackendService.PortResolution?
    ) -> ConnectionPresentation.EngineOwnership {
        if strategy.connectsToRemoteHost { return .remote }

        // Cannot start it. This is the case that was already right by accident:
        // a Dev Local engine reached over UDS is `.ownedEmbedded` to the process
        // layer (the app SIGTERMs it at quit), but `adoptDebugExternalEngine`
        // has no spawn path at all, so "Restart Engine" would strand the user
        // with a stopped engine and no way to start one.
        guard strategy.spawnsBundledEngine else { return .externalLocal }

        // Cannot stop it. One table, shared with the process layer, so the two
        // answers can no longer drift apart in a refactor.
        let process = EmbeddedBackendService.engineOwnership(
            strategy: strategy,
            transportMode: transportMode,
            portResolution: portResolution
        )
        return process == .ownedEmbedded ? .appManaged : .externalLocal
    }
}

extension EmbeddedBackendService {

    /// What the connection surfaces may offer for the engine this launch
    /// actually reached (#4400).
    ///
    /// The live counterpart of the pure `resolve` above, reading the same
    /// inputs `currentEngineOwnership` reads. Before a launch has recorded
    /// them there is nothing to know beyond the strategy, so it falls back to
    /// the strategy-only answer rather than guessing at a port resolution that
    /// has not happened yet.
    var connectionOwnership: ConnectionPresentation.EngineOwnership {
        let strategy = lastProvisioningStrategy ?? EngineConfig.engineProvisioningStrategy()
        return .resolve(
            strategy: strategy,
            transportMode: lastTransportMode ?? EngineConfig.transportMode(for: strategy),
            portResolution: lastPortResolution
        )
    }
}
