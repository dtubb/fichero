import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
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
    /// Which read a footer line came from: the run list, or the jobs poll (#5469).
    private enum LoadSource: Int { case runs, jobs }
    private struct LoadFailureKey: Hashable {
        let library: UUID
        let source: LoadSource
    }
    /// The footer's lines (`activity.window.honest-state`, #5431): one per
    /// library and read whose last load failed, naming the cause. Keyed so the
    /// next successful load of that read clears exactly its own line.
    private var loadFailures: [LoadFailureKey: String] = [:]
    var runLoadFailures: [String] {
        let ordered = loadFailures
            .sorted { ($0.key.library.uuidString, $0.key.source.rawValue) < ($1.key.library.uuidString, $1.key.source.rawValue) }
            .map(\.value)
        // The run list and the jobs poll refused for the same reason say it once.
        var seen: Set<String> = []
        return ordered.filter { seen.insert($0).inserted }
    }

    /// Set ONE footer line, or clear it with nil; untouched when unchanged.
    private func setLoadFailure(_ message: String?, library: UUID, source: LoadSource) {
        let key = LoadFailureKey(library: library, source: source)
        if loadFailures[key] != message { loadFailures[key] = message }
    }

    /// The library this store belongs to, named in a jobs-poll footer line (#5469).
    @ObservationIgnored private weak var library: LibraryManager.LibraryReference?
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
    /// Pause Background Work is on (`activity.pause.global`), from the same read.
    private(set) var backgroundPaused = false
    /// This Mac's state (memory, heat, battery, in use, why heavy work waits), same read.
    private(set) var machine: Components.Schemas.MachineState?
    private var jobsPollTask: Task<Void, Never>?

    // MARK: - Run trees (#5415: the Activity table's run → step → page rows)
    //
    // `GET /api/activity/jobs/{threadId}` per run, keyed by thread id. A tree
    // is fetched when its row is first shown and again when the change stream
    // names its run: ONE key patched, never the whole dictionary replaced.
    private(set) var runTrees: [String: ActivityJobNode] = [:]
    /// Runs the engine has no tree for (recorded before the jobs table): not
    /// asked again, their row shows the run alone.
    private var runsWithoutTree: Set<String> = []
    private var treeFetchesInFlight: Set<String> = []
    /// One pending tree read per run, restarted by each frame of a burst.
    @ObservationIgnored private var pendingTreeReads: [String: Task<Void, Never>] = [:]
    private let treeReadDelay: Duration = .milliseconds(300)
    /// How often the jobs endpoint is polled. Loopback + a point-in-time read,
    /// so 2s is live enough for a progress bar without adding real load.
    private let jobsPollInterval: Duration = .seconds(2)

    init(service: ActivityService, library: LibraryManager.LibraryReference? = nil) {
        self.activityService = service
        self.library = library
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
            if processCpuPercent != snapshot.processCpuPercent { processCpuPercent = snapshot.processCpuPercent }
            if cpuCount != snapshot.cpuCount { cpuCount = snapshot.cpuCount }
            if backgroundPaused != snapshot.paused { backgroundPaused = snapshot.paused }
            if machine != snapshot.machine { machine = snapshot.machine }
            if let library { setLoadFailure(nil, library: library.id, source: .jobs) }
        } catch {
            // A refusal is a standing answer, not a blip: it reaches the footer
            // with its cause, through the run list's own message (#5469).
            // Anything else (a restarting engine) stays quiet; the next tick recovers.
            guard let library, Self.isRefusal(error) else {
                log.debug("ActivityStore: jobs poll failed \(error.localizedDescription, privacy: .public)")
                return
            }
            let message = Self.runLoadFailureMessage(libraryName: library.displayName, error: error)
            log.error("ActivityStore: jobs poll refused: \(message, privacy: .public)")
            setLoadFailure(message, library: library.id, source: .jobs)
        }
    }

    private static func isRefusal(_ error: Error) -> Bool {
        switch AccessError.classify((error as? ClientError)?.underlyingError ?? error) {
        case .unauthenticated, .staleBootstrapToken, .deviceAccessExpired, .forbidden: return true
        default: return false
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
            setLoadFailure(nil, library: library.id, source: .runs)
        } catch {
            let message = Self.runLoadFailureMessage(libraryName: library.displayName, error: error)
            log.error("ActivityStore: run list load failed: \(message, privacy: .public)")
            setLoadFailure(message, library: library.id, source: .runs)
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

    /// The footer line for a failed run-list or jobs load: the library AND the
    /// cause (#5431). A refusal (401/403, e.g. an engine respawn's token change)
    /// and an engine that cannot be reached are different fixes, so they read
    /// differently; anything else carries its own description. A 403 names the
    /// cause the engine's typed body gives (#5469): the project's location
    /// (`library_outside_allowed_locations`, the roots check) is not the app's
    /// credentials, and any other coded refusal reads as the engine wrote it.
    static func runLoadFailureMessage(libraryName: String, error: Error) -> String {
        let cause: String
        switch AccessError.classify((error as? ClientError)?.underlyingError ?? error) {
        case .forbidden(let reason, _) where reason == AccessError.outsideAllowedLocations:
            cause = "the engine isn't allowed to open the project from where it's saved"
        case .forbidden(_?, let message?):
            cause = message
        case .unauthenticated, .staleBootstrapToken, .deviceAccessExpired, .forbidden:
            cause = "the engine refused the app's credentials"
        case .engineUnreachable:
            cause = "the engine could not be reached"
        case let other:
            cause = other.localizedDescription
        }
        return "Couldn't load activity from \(libraryName): \(cause)"
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

    /// A run straight from the runs table, not an event. `startedAt` is read
    /// with the one engine-date parser (fractional seconds, any offset); a
    /// time it cannot read is `nil`, shown as unknown and logged, never
    /// replaced by "now", which made every row say "just now" (#5432).
    private func historicalRun(
        from summary: Components.Schemas.WorkflowRunSummary,
        library: LibraryManager.LibraryReference
    ) -> ActivityRun {
        let timestamp = summary.startedAt.flatMap(parseEngineDate)
        if timestamp == nil {
            let raw = summary.startedAt ?? "nil"
            log.error("ActivityStore: run \(summary.threadId, privacy: .public) has an unreadable started_at \(raw, privacy: .public)")
        }
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
            libraryName: library.displayName,
            failureReason: (summary.error?.isEmpty == false) ? summary.error : nil
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
        // The Activity table's row for this run (#5415): re-read ITS tree only,
        // once the burst settles — one row updated in place, no list reload.
        if let threadId = activity.threadId, runTrees[threadId] != nil {
            scheduleTreeRead(threadId: threadId)
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

// MARK: - Run trees (#5415): the Activity table's run → step → page rows

extension ActivityStore {
    /// Fetch one run's tree once, when its row is first shown. Later reads
    /// come from the change stream (`applyActivityEvent`), never a poll.
    func loadRunTree(threadId: String) async {
        guard runTrees[threadId] == nil, !runsWithoutTree.contains(threadId) else { return }
        await fetchRunTree(threadId: threadId)
    }

    /// Read one run's tree and patch that ONE key. A failed read keeps what
    /// the row showed; a run the engine has no tree for is remembered.
    private func fetchRunTree(threadId: String) async {
        guard !treeFetchesInFlight.contains(threadId) else { return }
        treeFetchesInFlight.insert(threadId)
        defer { treeFetchesInFlight.remove(threadId) }
        do {
            if let tree = try await activityService.getJobTree(id: threadId) {
                if runTrees[threadId] != tree { runTrees[threadId] = tree }
            } else {
                runsWithoutTree.insert(threadId)
            }
        } catch {
            log.debug("ActivityStore: tree for \(threadId, privacy: .public) failed \(error.localizedDescription, privacy: .public)")
        }
    }

    /// Pause or resume one row's job (`activity.pause.per-job`) and set the
    /// state the engine answers on that ONE node in place. `runThreadId` is
    /// the run whose tree holds it. Returns what went wrong, in words, or nil.
    func setJobPaused(jobId: String, paused: Bool, runThreadId: String?) async -> String? {
        do {
            let state = try await activityService.setJobPaused(id: jobId, paused: paused)
            patchJobState(state, jobId: jobId, runThreadId: runThreadId)
            return nil
        } catch {
            return error.localizedDescription
        }
    }

    /// Stop one row's job and what is under it (the audited `job.cancel`).
    func cancelJob(jobId: String, runThreadId: String?) async -> String? {
        do {
            let state = try await activityService.cancelJob(id: jobId)
            patchJobState(state, jobId: jobId, runThreadId: runThreadId)
            return nil
        } catch {
            return error.localizedDescription
        }
    }

    /// Read the pages a finished run did not do (#5555): the engine starts one
    /// new run; the run list picks it up on the next resync. Returns what went
    /// wrong, in words, or nil.
    func readPagesAgain(runThreadId: String) async -> String? {
        do {
            _ = try await activityService.readPagesAgain(threadId: runThreadId)
            await resync()
            return nil
        } catch {
            return error.localizedDescription
        }
    }

    private func scheduleTreeRead(threadId: String) {
        pendingTreeReads[threadId]?.cancel()
        pendingTreeReads[threadId] = Task { [weak self] in
            guard let delay = self?.treeReadDelay else { return }
            try? await Task.sleep(for: delay)
            guard !Task.isCancelled, let self else { return }
            self.pendingTreeReads[threadId] = nil
            await self.fetchRunTree(threadId: threadId)
        }
    }

    private func patchJobState(_ state: String, jobId: String, runThreadId: String?) {
        guard let runThreadId, let tree = runTrees[runThreadId],
              let changed = tree.settingState(state, of: jobId) else { return }
        runTrees[runThreadId] = changed
    }
}
