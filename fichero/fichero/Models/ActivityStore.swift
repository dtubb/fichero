import Foundation
import Observation
import OSLog

/// Per-library activity store (#2448).
///
/// Single point for activity/run data in the library.  Views never call
/// `ActivityServiceGenerated` directly: they observe `refreshToken` and call
/// `loadRuns()` / `loadItems()` through the store.
///
/// **Live-refresh strategy:**
/// `ActivityStore` listens to `/api/activity/stream`, so runs started in any
/// window or restored by the backend refresh the browser from activity events.
@MainActor
@Observable
final class ActivityStore: ChangeEventConsumer {
    // ─── Service ──────────────────────────────────────────────────────────────
    let activityService: ActivityServiceGenerated

    // ─── Refresh signal (views observe this) ──────────────────────────────────
    /// Bumped whenever an activity SSE event arrives or a reconnect resync fires.
    /// `ActivityBrowserView` observes this to reload its run list.
    private(set) var refreshToken: Int = 0

    private let log = Logger(subsystem: "app.fichero.fichero", category: "ActivityStore")
    private let streamService: ActivityStreamService

    /// When set (REMOTE hosts only), folded change frames arriving on
    /// `/api/activity/stream` (#3159) are reconstructed into `ChangeEvent`s and
    /// handed here — wired by `LibraryReference` to the change stream's
    /// `ingest(_:)` so the domain stores update in place, exactly as a native
    /// `/changes/stream` event would (#2479). Nil on local hosts, where those
    /// mutations already arrive on the dedicated change stream (no double-apply).
    var changeRouter: (@MainActor (ChangeEvent) -> Void)?

    init(service: ActivityServiceGenerated) {
        self.activityService = service
        self.streamService = ActivityStreamService(activityService: service)
    }

    func start() {
        streamService.start { [weak self] activity in
            self?.applyActivityEvent(activity)
        }
    }

    func stop() {
        streamService.stop()
    }

    /// True when the activity SSE stream has dropped and runs are no longer
    /// refreshing live (F7). Views show a "live updates paused" pill. Reads the
    /// nested @Observable stream service, so observers of this store re-render
    /// when it flips.
    var liveUpdatesPaused: Bool { streamService.liveUpdatesUnavailable }

    /// True when the activity stream was refused with a 403 — this device has no
    /// role on the library. A terminal state (no auto-retry): the UI shows an
    /// access-denied affordance rather than a reconnect spinner (#2479).
    var liveUpdatesAccessDenied: Bool { streamService.accessDenied }

    /// Force an immediate reconnect of the activity stream (the pill's action),
    /// rather than waiting out the backoff.
    func reconnectLiveUpdates() {
        stop()
        start()
    }

    // MARK: - ChangeEventConsumer

    /// Activity refresh is driven by `/activity/stream`, not workflow-definition
    /// events. Keep this consumer only so change-stream reconnects can resync.
    nonisolated var changeDomains: Set<String> { [] }

    func apply(_ event: ChangeEvent) {
        log.debug("ActivityStore ignored change event \(event.type, privacy: .public)")
    }

    func resync() async {
        refreshToken += 1
        log.debug("ActivityStore: resync, refreshToken → \(self.refreshToken, privacy: .public)")
    }

    func applyActivityEvent(_ activity: ActivityItem) {
        // #3159 folds per-library mutations onto the activity stream so REMOTE
        // subscribers see them (the dedicated /changes/stream can drop over the
        // tailnet, #2479). Such a frame carries `change_type` in its metadata:
        // reconstruct the ChangeEvent and fan it to the domain stores instead of
        // treating it as a run update. It must NOT bump `refreshToken` — that
        // would reload the whole run list on every mutation (no-wholesale
        // re-render). `changeRouter` is nil on local hosts (those changes arrive
        // on the dedicated stream), so a folded frame is simply dropped there.
        if let metadata = activity.metadataStrings,
           let change = ChangeEvent(activityMetadata: metadata) {
            changeRouter?(change)
            log.debug("ActivityStore: folded change \(change.type, privacy: .public) routed=\(self.changeRouter != nil, privacy: .public)")
            return
        }
        refreshToken += 1
        log.debug("ActivityStore: activity event \(activity.type, privacy: .public), refreshToken → \(self.refreshToken, privacy: .public)")
    }
}
