import Foundation

extension ActivityStore {
    /// The wait before the next jobs read (#6446): the failure back-off, and a window nobody can see (the app hidden or every window
    /// minimised or covered) waits at least 30 s, so a large library is not queried for a screen no one is looking at.
    static func jobsPollWait(failures: Int, windowVisible: Bool, base: Duration) -> Duration {
        let wait = failures == 0 ? base : pollInterval(afterFailures: failures)
        return windowVisible ? wait : max(wait, .seconds(30))
    }

    /// Whether any window of the app can be seen; the app sets it from AppKit's occlusion state at launch (`AppState.init`).
    nonisolated(unsafe) static var anyWindowVisible: @Sendable () -> Bool = { true }

    /// `jobsPollWait` for the window as it is now.
    static func nextJobsPollWait(failures: Int, base: Duration) -> Duration {
        jobsPollWait(failures: failures, windowVisible: anyWindowVisible(), base: base)
    }
}
