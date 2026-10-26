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

    /// How many missed pings in a row before the app restarts the engine.
    static func failuresBeforeRestart(workRunning: Bool) -> Int {
        (workRunning ? hungWithWorkSeconds : hungSeconds) / pingSeconds
    }
}
