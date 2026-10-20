import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

extension ActivityStore {
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

        // A run deleted here stays deleted although its execution is still in memory (#5634).
        let live = activeExecutions.filter { !deletedRunIds.contains($0.threadId) }
            .map { liveRun(from: $0, library: library) }
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

    /// Whether the runs loaded so far may leave out runs that ended today: more exist, and the oldest loaded run is itself
    /// from today (DONE TODAY would miss what is on the next page). A run whose date is unknown stops the paging: it
    /// would never end (## 749).
    func mayHaveMoreRunsToday(now: Date = Date(), calendar: Calendar = .current) -> Bool {
        guard runsHasMore, !runs.isEmpty else { return false }
        let dates = runs.map { $0.completedAt ?? $0.timestamp }
        guard !dates.contains(where: { $0 == nil }), let oldest = dates.compactMap({ $0 }).min() else { return false }
        return oldest >= calendar.startOfDay(for: now)
    }

    /// Page in older runs until the loaded ones reach back past today, so DONE TODAY is whole whether or not its rows are
    /// drawn (the window's rows page the list only when they appear, and DONE TODAY is collapsed). Stops when a page adds
    /// nothing.
    func loadRunsForToday(library: LibraryManager.LibraryReference, now: Date = Date(), calendar: Calendar = .current) async {
        while mayHaveMoreRunsToday(now: now, calendar: calendar) {
            let before = historicalRunsFetched
            await loadMoreRuns(library: library)
            if historicalRunsFetched == before { return }
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
            deletedRunIds.formUnion(deleted)
            runs.removeAll { deleted.contains($0.runId) }
            return RunDeleteOutcome(deletedIds: result.deletedIds, skippedIds: result.skippedIds)
        } catch {
            log.error("ActivityStore: deleteRuns failed \(error.localizedDescription, privacy: .public)")
            return RunDeleteOutcome(deletedIds: [], skippedIds: threadIds ?? [], failure: error.localizedDescription)
        }
    }

    /// Clear Failed in this project (`activity.window.clear-failed`, #5634):
    /// its failed runs deleted (`deleteRuns(statuses:)`) and its failed jobs of
    /// their own cleared (`job.clear_failed`), each cleared row removed in place
    /// and the jobs read taken again. Before, only runs were deleted, so a
    /// failed job's row (and the toolbar's error glyph) never went away.
    func clearFailed() async -> ClearFailedOutcome {
        let deletedRuns = await deleteRuns(statuses: ["failed"])
        var outcome = ClearFailedOutcome(
            runsCleared: deletedRuns.deletedIds.count,
            runsSkipped: deletedRuns.skippedIds.count,
            failures: deletedRuns.failure.map { [$0] } ?? []
        )
        do {
            let cleared = Set(try await activityService.clearFailedJobs())
            outcome.jobsCleared = cleared.count
            if backgroundJobs.contains(where: { cleared.contains($0.id) }) {
                backgroundJobs.removeAll { cleared.contains($0.id) }
            }
            await refreshBackgroundJobs()
        } catch {
            log.error("ActivityStore: clear failed jobs failed \(error.localizedDescription, privacy: .public)")
            outcome.failures.append(error.localizedDescription)
        }
        return outcome
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
        // The always-there project has no name: no "from" (never "from : …").
        guard let project = ActivityRun.projectLabel(libraryName) else {
            return "Couldn't load activity: \(cause)"
        }
        return "Couldn't load activity from \(project): \(cause)"
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
            failureReason: (summary.error?.isEmpty == false) ? summary.error : nil,
            completedAt: summary.completedAt.flatMap(parseEngineDate)
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
        // once the burst settles — one row updated in place, no list reload. A
        // run that is a stage of a recipe run (#5576) re-reads the recipe run's
        // tree, which holds it: the stage's pages done and left follow live.
        if let threadId = activity.threadId {
            if runTrees[threadId] != nil { scheduleTreeRead(threadId: threadId) }
            for key in recipeRunTrees(holdingStage: threadId) { scheduleTreeRead(threadId: key) }
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
