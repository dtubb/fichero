import Foundation

/// When the app may restart a LIVE engine (`engine.restart-waits-for-the-work`, #6176; owner 2026-10-26: "far too aggressive").
/// A missed health ping only means the engine is busy: Kraken, an import or an embed can hold its event loop for many
/// seconds. The app restarts it only after it has not answered for `hungSeconds`, and for `hungWithWorkSeconds` while an
/// import or a job is running; before that it waits and says it is busy. Pure, so the patience is tested without an engine.
enum EngineRestartPolicy {
    /// The heartbeat pings this often (`AppState.startBackendHeartbeat`).
    static let pingSeconds = 5
    /// No answer for this long, with nothing running: the engine is hung.
    static let hungSeconds = 180
    /// No answer for this long while an import or a job is running.
    static let hungWithWorkSeconds = 600

    /// Jobs running in the engine, from the Activity poll (`ActivityStore`): the heartbeat's patience counts them (#6176).
    @MainActor static var runningJobs = 0

    /// A paired Mac the app cannot restart anyway: after this many missed pings it only looks for another endpoint or
    /// says it is unreachable, so the wait stays short (about 15 s).
    static let remoteFailures = 3

    /// How many missed pings in a row before the app acts on the engine: restarts a local one, or gives up on a remote one.
    static func failuresBeforeRestart(workRunning: Bool, isLocal: Bool = true) -> Int {
        guard isLocal else { return remoteFailures }
        return (workRunning ? hungWithWorkSeconds : hungSeconds) / pingSeconds
    }

    /// The wait after restart `attempt` fails, before the next: doubling from 10 s, capped at 5 minutes.
    static func backoffSeconds(afterAttempt attempt: Int) -> Int {
        min(10 << min(max(attempt - 1, 0), 5), 300)
    }

    /// Whether `failures` missed pings in a row call for action now.
    static func shouldRestart(failures: Int, workRunning: Bool, isLocal: Bool = true) -> Bool {
        failures >= failuresBeforeRestart(workRunning: workRunning, isLocal: isLocal)
    }
}
