import FicheroAPIClient
import SwiftUI

extension BackendConnectionView {
    /// Who owns the engine PROCESS for this build/launch — the input that
    /// decides whether "Restart Engine" is a truthful offer (#4380).
    ///
    /// Reads the LIVE service, not the strategy (#4400). The strategy alone
    /// cannot see that this launch adopted an engine it did not spawn, so it
    /// said `.appManaged` for a process `beginStop` refuses to signal — and
    /// this popover is the one surface that turns that answer into a button.
    /// `EmbeddedBackendService.engineOwnership` is the shared table both
    /// answers now come from; the two questions still differ, and
    /// `ConnectionPresentation+Ownership.swift` says why.
    var engineProcessOwnership: ConnectionPresentation.EngineOwnership {
        backendService.connectionOwnership
    }

    /// The ONE status this popover renders, derived from the same mapping the
    /// status island and the library pane read (#4380). The view never invents
    /// copy of its own — including "is this a failure", which is now simply
    /// `connectionStatus.isError` instead of a second phase switch that could
    /// disagree with the first.
    var connectionStatus: ConnectionPresentation.Display {
        ConnectionPresentation.status(
            phase: appState.engine.phase,
            ownership: engineProcessOwnership,
            accessError: failureAccessError,
            authBroken: appState.authBroken
        )
    }

    static func usesAppManagedEmbeddedEngine(
        _ strategy: EngineConfig.EngineProvisioningStrategy
    ) -> Bool {
        strategy.spawnsBundledEngine
    }

    /// The holding PID when the engine is in the `portConflict` phase (#3111),
    /// else nil. Drives whether "Stop it" is offerable.
    ///
    /// nil does NOT mean "no conflict" — under App Sandbox the holder's PID is
    /// unknowable (no lsof), so the App Store build reports `portConflict(nil)`
    /// (#3749). Ask `isPortConflict` for "are we in the conflict phase"; ask this
    /// only for "do we know who to stop".
    var portConflictPID: Int? {
        if case .portConflict(let pid) = appState.engine.phase { return pid }
        return nil
    }

    /// In the `portConflict` phase, PID known or not. Gates the recovery actions
    /// — keyed off the phase rather than the PID so a sandboxed conflict renders
    /// Use it / Quit instead of an empty box.
    var isPortConflict: Bool {
        if case .portConflict = appState.engine.phase { return true }
        return false
    }

    var failureAccessError: AccessError? {
        appState.backendAccessError ?? (appState.authBroken ? .unauthenticated : nil)
    }
}
