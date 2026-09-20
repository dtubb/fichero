import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// Per-library activity store (#2448).
///
/// Single point for activity/run data in the library.  Views never call
/// `ActivityService` directly: they observe `refreshToken` and call
/// `loadRuns()` / `loadItems()` through the store.
///
/// **Live-refresh strategy:**
/// `ActivityStore` listens to `/api/activity/stream`, so runs started in any
/// window or restored by the backend refresh the browser from activity events.
@MainActor
@Observable
final class ActivityStore: ChangeEventConsumer {
    // ─── Service ──────────────────────────────────────────────────────────────
    let activityService: ActivityService

    // ─── Refresh signal (views observe this) ──────────────────────────────────
    /// Bumped whenever an activity SSE event arrives or a reconnect resync fires.
    /// `ActivityBrowserView` observes this to reload its run list.
    private(set) var refreshToken: Int = 0
    /// Coalesces activity-frame bursts into one refreshToken bump (see
    /// `applyActivityEvent`).
    private let refreshDebouncer = ReloadDebouncer()

    private let log = Logger(subsystem: "app.fichero.fichero", category: "ActivityStore")
    private let streamService: ActivityStreamService

    /// When set (REMOTE hosts only), folded change frames arriving on
    /// `/api/activity/stream` (#3159) are reconstructed into `ChangeEvent`s and
    /// handed here — wired by `LibraryReference` to the change stream's
    /// `ingest(_:)` so the domain stores update in place, exactly as a native
    /// `/changes/stream` event would (#2479). Nil on local hosts, where those
    /// mutations already arrive on the dedicated change stream (no double-apply).
    var changeRouter: (@MainActor (ChangeEvent) -> Void)?

    // ─── Backend-work surface (#2279) ──────────────────────────────────────────
    /// The most recent in-flight backend task (e.g. an import or batch the engine
    /// or CLI kicked off), or `nil` when nothing is running. Views observe this
    /// for a live progress indicator. Updated in place — a backend-work frame
    /// never bumps `refreshToken`, so it can't trigger a run-list reload.
    private(set) var backendWork: BackendWorkStatus?

    /// The most recent "library opened" signal — e.g. the CLI opened a library
    /// out of band (#2279). Views surface it subtly so the user knows the backend
    /// touched a library they didn't open in this window.
    private(set) var lastLibraryOpened: LibraryOpenedSignal?

    // MARK: - Run list (#3231, #4960)
    //
    // The store owns the live+history run-list merge (previously assembled
    // inside ActivityBrowserView). Views observe `runs`/`runLoadFailures` and
    // call `rebuildRuns`, passing @Environment deps in. `runs` is patched
    // in place (`patchRun`) — no method here reassigns the whole array.
    private(set) var runs: [ActivityRun] = []
    private(set) var runLoadFailures: [String] = []
    private(set) var isRebuildingRuns = false
    /// True when the last `GET /workflow-execution/runs` page was full —
    /// probably a next page to page in. `false` on a short page, or before load.
    private(set) var runsHasMore = false
    /// Historical rows fetched so far (reset by `rebuildRuns`) — the `offset`
    /// `loadMoreRuns` pages from.
    private var historicalRunsFetched = 0
    /// One page at a time — the old 7-day/100-event ceiling is gone, so the
    /// list can be arbitrarily long ("show ALL items"); page it instead.
    private let runsPageSize = 50

    // MARK: - Background jobs (#user-machine-always-useful FIX 2)
    //
    // The single source both the toolbar Activity popover and the full Activity
    // viewer read for live background jobs (embedding, derivative/HTR queues,
    // Kraken Detect Regions, …) + rough process CPU%. `GET /api/activity/jobs`
    // is polled here — global, cheap, no SSE frame for it — and the two
    // surfaces observe these properties, so they cannot disagree about what is
    // running or whether it FAILED. Updated in place, only when the value
    // actually changes (no-wholesale-rerender): a steady 100%-idle poll never
    // invalidates the observing views.
    private(set) var backgroundJobs: [ActivityJob] = []
    private(set) var processCpuPercent: Double?
    private(set) var cpuCount: Int = 0
    private var jobsPollTask: Task<Void, Never>?
    /// How often the jobs endpoint is polled. Loopback + a point-in-time read,
    /// so 2s is live enough for a progress bar without adding real load.
    private let jobsPollInterval: Duration = .seconds(2)

    init(service: ActivityService) {
        self.activityService = service
        self.streamService = ActivityStreamService(activityService: service)
    }

    func start() {
        streamService.start { [weak self] activity in
            self?.applyActivityEvent(activity)
        }
        startJobsPolling()
    }

    func stop() {
        streamService.stop()
        jobsPollTask?.cancel()
        jobsPollTask = nil
    }

    // MARK: - Background-jobs polling

    /// Poll `GET /api/activity/jobs` on a loop until `stop()`. Started by
    /// `start()` so the toolbar's Activity glyph reflects background work even
    /// with no Activity surface open.
    private func startJobsPolling() {
        jobsPollTask?.cancel()
        jobsPollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refreshBackgroundJobs()
                guard let interval = self?.jobsPollInterval else { return }
                try? await Task.sleep(for: interval)
            }
        }
    }

    /// Read one jobs snapshot and apply it in place. A poll failure (engine
    /// restarting, brief transport drop) keeps the last snapshot rather than
    /// flapping the surfaces to empty — the next tick recovers.
    func refreshBackgroundJobs() async {
        do {
            let snapshot = try await activityService.getBackgroundJobs()
            if backgroundJobs != snapshot.jobs { backgroundJobs = snapshot.jobs }
            if processCpuPercent != snapshot.processCpuPercent {
                processCpuPercent = snapshot.processCpuPercent
            }
            if cpuCount != snapshot.cpuCount { cpuCount = snapshot.cpuCount }
        } catch {
            log.debug("ActivityStore: jobs poll failed \(error.localizedDescription, privacy: .public)")
        }
    }

    /// Background jobs the backend reports as FAILED — surfaced distinctly so a
    /// silent failure (Kraken not installed) can't be mistaken for "still
    /// working" and re-run. Derived so both surfaces agree on the set.
    var failedJobs: [ActivityJob] { backgroundJobs.filter { $0.state.isFailed } }

    /// Background jobs still consuming compute — counts toward the toolbar
    /// badge and the popover's active-task list.
    var activeJobs: [ActivityJob] { backgroundJobs.filter { $0.state.isActive } }

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

    // MARK: - Run list assembly (#3231, #4960)

    /// Rebuild `runs` from the window's live executions + this library's
    /// FIRST page of runs. #4960: reads the engine's `workflow_runs` table —
    /// the SAME record `/activity/jobs` (the popover) already reads —
    /// instead of the old 7-day/100-event log, the verified cause of the
    /// popover and window disagreeing (`agent-work/reviews/
    /// activity-system-review-2026-09-20.md` §2). Every fresh row is PATCHED
    /// into `runs`, never a wholesale replace. Fetches through
    /// `self.activityService`, not `library.activityService` (identical by
    /// construction) — a store built directly in a test needs no
    /// `LibraryReference` transport.
    func rebuildRuns(
        activeExecutions: [WorkflowExecution],
        library: LibraryManager.LibraryReference
    ) async {
        isRebuildingRuns = true
        defer { isRebuildingRuns = false }

        let live = activeExecutions.map { liveRun(from: $0, library: library) }
        let liveIds = Set(live.map(\.id))
        do {
            let page = try await activityService.listWorkflowRuns(limit: runsPageSize, offset: 0)
            let historical = page.items
                .filter { !liveIds.contains(historicalRunId(threadId: $0.threadId, library: library)) }
                .map { historicalRun(from: $0, library: library) }
            for run in live + historical {
                patchRun(run)
            }
            historicalRunsFetched = page.items.count
            runsHasMore = page.items.count >= runsPageSize
            runLoadFailures.removeAll { $0 == loadFailureMessage(for: library) }
        } catch {
            if !runLoadFailures.contains(loadFailureMessage(for: library)) {
                runLoadFailures.append(loadFailureMessage(for: library))
            }
        }
    }

    /// Page in the NEXT page of this library's historical runs, appended —
    /// never replacing what `runs` already holds. A no-op while there is no
    /// further page, or a rebuild is already in flight.
    func loadMoreRuns(library: LibraryManager.LibraryReference) async {
        guard runsHasMore, !isRebuildingRuns else { return }
        do {
            let page = try await activityService.listWorkflowRuns(
                limit: runsPageSize,
                offset: historicalRunsFetched
            )
            for summary in page.items {
                patchRun(historicalRun(from: summary, library: library))
            }
            historicalRunsFetched += page.items.count
            runsHasMore = page.items.count >= runsPageSize
        } catch {
            // A page-in failure leaves `runs` exactly as it was; scrolling
            // again retries.
        }
    }

    /// Update ONE row in place by id, at its EXISTING array position (same
    /// identity for a future Table's selection/scroll); a run not yet
    /// present is appended. The only way `runs` content ever changes.
    func patchRun(_ run: ActivityRun) {
        if let index = runs.firstIndex(where: { $0.id == run.id }) {
            runs[index] = run
        } else {
            runs.append(run)
        }
    }

    /// Delete runs by explicit id OR by a status filter — "Clear Failed" is
    /// this SAME call with `statuses: ["failed"]`. Removes exactly the
    /// `deletedIds` the engine reports; `skippedIds` (still-running, unknown)
    /// keep their row, returned so the caller can say so plainly.
    @discardableResult
    func deleteRuns(threadIds: [String]? = nil, statuses: [String]? = nil) async -> RunDeleteOutcome {
        do {
            let result = try await activityService.deleteWorkflowRuns(threadIds: threadIds, statuses: statuses)
            let deleted = Set(result.deletedIds)
            runs.removeAll { deleted.contains($0.runId) }
            return RunDeleteOutcome(deletedIds: result.deletedIds, skippedIds: result.skippedIds)
        } catch {
            log.debug("ActivityStore: deleteRuns failed \(error.localizedDescription, privacy: .public)")
            return RunDeleteOutcome(deletedIds: [], skippedIds: threadIds ?? [])
        }
    }

    private func loadFailureMessage(for library: LibraryManager.LibraryReference) -> String {
        "Couldn't load activity from \(library.displayName)"
    }

    private func liveRun(
        from execution: WorkflowExecution,
        library: LibraryManager.LibraryReference
    ) -> ActivityRun {
        ActivityRun(
            id: historicalRunId(threadId: execution.threadId, library: library),
            runId: execution.threadId,
            workflowId: execution.id,
            threadId: execution.threadId,
            workflowName: activityCleanWorkflowName(execution.name),
            timestamp: execution.startTime,
            status: activityMapExecutionStatus(execution.status),
            progress: execution.overallProgress,
            currentStep: execution.currentNodeName,
            errorCount: execution.nodeStates.values.reduce(0) { $0 + $1.errorCount },
            fileCount: execution.totalFiles,
            isLive: true,
            libraryId: library.id,
            libraryName: library.displayName
        )
    }

    /// A run straight from the runs table, not an event. An unparseable or
    /// absent `startedAt` falls back to "now" rather than sorting a row to
    /// the top or bottom by accident.
    private func historicalRun(
        from summary: Components.Schemas.WorkflowRunSummary,
        library: LibraryManager.LibraryReference
    ) -> ActivityRun {
        let timestamp = summary.startedAt.flatMap { ISO8601DateFormatter().date(from: $0) } ?? Date()
        return ActivityRun(
            id: historicalRunId(threadId: summary.threadId, library: library),
            runId: summary.threadId,
            workflowId: summary.workflowId,
            threadId: summary.threadId,
            workflowName: activityCleanWorkflowName(summary.workflowName),
            timestamp: timestamp,
            status: activityMapRunStatus(summary.status),
            progress: nil,
            currentStep: nil,
            errorCount: (summary.error?.isEmpty == false) ? 1 : 0,
            fileCount: summary.documentCount ?? 0,
            isLive: false,
            libraryId: library.id,
            libraryName: library.displayName
        )
    }

    /// A live run and its later-settled historical record share this id —
    /// what lets `patchRun` update a finishing run's row IN PLACE.
    private func historicalRunId(threadId: String, library: LibraryManager.LibraryReference) -> String {
        "\(library.id.uuidString)|\(threadId)"
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
        // Backend-work / library-opened signals (#2279) ride the same folded
        // frames but are informational, not domain mutations — intercept them
        // first and update the observable indicator IN PLACE (no run-list
        // reload, no domain-store fan-out).
        if let metadata = activity.metadataStrings,
           let signal = BackendActivityEvent(activityMetadata: metadata) {
            applyBackendSignal(signal)
            return
        }
        // #3159 folds per-library mutations onto the activity stream so REMOTE
        // subscribers see them (the dedicated /changes/stream can drop over the
        // tailnet, #2479). Such a frame carries `change_type` in its metadata:
        // reconstruct the ChangeEvent and fan it to the domain stores instead of
        // treating it as a run update. It must NOT bump `refreshToken` — that
        // would reload the whole run list on every mutation (no-wholesale
        // re-render).
        //
        // CHEAP-DROP ON LOCAL (2026-09-06): `changeRouter` is nil on local hosts
        // — the same mutations already arrive on the dedicated /changes/stream,
        // so the folded copy is pure waste there. Detect the folded frame by its
        // `change_type` key (one dict lookup, the same guard ChangeEvent's init
        // uses) and, when there is no router, drop it WITHOUT reconstructing the
        // ChangeEvent — whose init JSON-decodes up to five id lists per frame —
        // and WITHOUT the per-frame log. Bulk embedding fires a `document.updated`
        // per doc; that flooded this branch 30+ times back-to-back on the main
        // actor (Daniel's Xcode console during an image-folder expand), each time
        // building an event nothing consumed. Still `return` in both cases: a
        // folded change must never fall through to the refresh burst below and
        // reload the run list.
        if let metadata = activity.metadataStrings,
           let changeType = metadata["change_type"], !changeType.isEmpty {
            if let route = changeRouter, let change = ChangeEvent(activityMetadata: metadata) {
                route(change)
                log.debug("ActivityStore: folded change \(change.type, privacy: .public) routed")
            }
            return
        }
        // Debounced (perf audit 2026-08-19): a running workflow emits several
        // activity frames per second, and every refreshToken bump used to fan
        // out to a full run-list refetch in the sidebar, the activity pane
        // AND the library's pending-status poll — ~10 GET /api/activity per
        // second for the whole run. One bump per burst carries the same
        // "something changed" signal.
        refreshDebouncer.schedule { [weak self] in
            await MainActor.run {
                guard let self else { return }
                self.refreshToken += 1
                self.log.debug("ActivityStore: activity burst, refreshToken → \(self.refreshToken, privacy: .public)")
            }
        }
    }

    /// Drive the live backend-work indicator from a decoded signal (#2279).
    /// Single-task model: `backendWork` tracks the latest running task and clears
    /// when THAT task reaches a terminal phase. (Concurrent backend tasks show
    /// the most recent; a multi-task queue view is a follow-up.)
    private func applyBackendSignal(_ signal: BackendActivityEvent) {
        switch signal {
        case .libraryOpened(let opened):
            lastLibraryOpened = opened
            log.debug(
                "ActivityStore: library.opened \(opened.libraryName, privacy: .public) via \(opened.source, privacy: .public)"
            )
        case .work(let status):
            if status.isTerminal {
                // Only clear if the finishing task is the one we're showing —
                // don't wipe a still-running task's indicator.
                if backendWork?.runId == status.runId {
                    backendWork = nil
                }
            } else {
                backendWork = status
            }
            log.debug(
                "ActivityStore: backend.work \(status.phase.rawValue, privacy: .public) \(status.taskName, privacy: .public)"
            )
        }
    }
}
