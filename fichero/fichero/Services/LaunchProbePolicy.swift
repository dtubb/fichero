import Foundation

/// iOS launch-connect policy (Daniel, 2026-08-29): iOS is remote-only — the app
/// dials the paired Mac — and that Mac being asleep, away, or off the network
/// must never hold the launch story hostage. The UI paints immediately with its
/// restored local state (BackendRootGate renders content in `.starting`); this
/// policy decides how long the launch probe may keep saying "Connecting…"
/// before the status flips to an honest "hasn't answered yet", while the
/// background retry (the same 5s heartbeat that recovers a mid-session drop)
/// keeps working the problem.
///
/// Pure values + functions in the `spawnWaitStep` pattern, so the whole policy
/// is unit-testable without a network, an engine, or UI.
enum LaunchProbePolicy {
    /// The transport's whole-request deadline is 60 seconds (#4379) — right for
    /// a data request, absurd as the time it takes to tell the user their Mac
    /// is not answering. Measured on-device 2026-08-29: with the paired Mac
    /// unreachable, every health request rode a ~60s NSURLError -1001 timeout
    /// and the launch story resolved at ~70s. The first probe now gets a few
    /// seconds of grace; the request itself keeps running past this deadline —
    /// only the STATUS stops waiting for it.
    static let firstProbeGrace: Duration = .seconds(3)

    /// What the launch task does when the grace period elapses before the probe
    /// answers. Only a probe still `.starting` flips to the honest
    /// still-connecting diagnosis; any phase the probe (or anything else)
    /// already resolved — ready, unreachable, authRejected, setupNeeded — is
    /// the truth and must never be overwritten by a stale race loser.
    static func actionOnGraceExpiry(phase: EngineSession.Phase) -> GraceExpiryAction {
        phase == .starting ? .markStillConnecting : .keepResolvedPhase
    }

    enum GraceExpiryAction: Equatable {
        case markStillConnecting
        case keepResolvedPhase
    }

    /// The honest status once the grace period is gone: names the host, says
    /// the app keeps trying, and says the library on screen is local state.
    static func stillConnectingDiagnosis(host: String) -> String {
        "Still trying to reach \(host) — it hasn't answered yet. "
            + "Fichero keeps retrying in the background; "
            + "your library is shown from its last local state."
    }
}
