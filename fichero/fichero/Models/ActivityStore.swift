import Foundation
import Observation
import OSLog

/// Per-library activity store (#2448).
///
/// Single point for activity/run data in the library.  Views never call
/// `ActivityServiceGenerated` directly: they observe `refreshToken` and call
/// `loadRuns()` / `loadItems()` through the store.
///
/// **Live-refresh strategy (no activity SSE domain today):**
/// The backend doesn't emit "activity" SSE events yet — it emits "workflow"
/// events when workflow *definitions* change.  `ActivityStore` listens to that
/// domain so any workflow-edit flushes the browser.  For in-flight runs the
/// `ActivityBrowserView` also polls every 5 s (see `ActivityBrowserView` task
/// body) and waits 2 s after the last execution finishes before the final
/// reload (covers the `workflow_completed` DB-write race).
@MainActor
@Observable
final class ActivityStore: ChangeEventConsumer {
    // ─── Service ──────────────────────────────────────────────────────────────
    let activityService: ActivityServiceGenerated

    // ─── Refresh signal (views observe this) ──────────────────────────────────
    /// Bumped whenever a workflow SSE event arrives or a reconnect resync fires.
    /// `ActivityBrowserView` observes this to reload its run list.
    private(set) var refreshToken: Int = 0

    private let log = Logger(subsystem: "app.fichero.fichero", category: "ActivityStore")

    init(service: ActivityServiceGenerated) {
        self.activityService = service
    }

    // MARK: - ChangeEventConsumer

    /// React to "workflow.*" SSE events — definition changes are adjacent to
    /// run creation, so they serve as a best-effort refresh trigger until the
    /// backend emits dedicated "activity.*" events.
    nonisolated var changeDomains: Set<String> { ["workflow"] }

    func apply(_ event: ChangeEvent) {
        refreshToken += 1
        log.debug("ActivityStore: workflow event \(event.verb, privacy: .public), refreshToken → \(self.refreshToken, privacy: .public)")
    }

    func resync() async {
        refreshToken += 1
        log.debug("ActivityStore: resync, refreshToken → \(self.refreshToken, privacy: .public)")
    }
}
