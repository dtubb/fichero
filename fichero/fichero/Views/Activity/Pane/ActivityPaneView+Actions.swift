import SwiftUI

/// The verbs the menu bar's Project › Activity reads from the focused Activity pane (`activity.pane.commands-through-the-table`):
/// which verbs the selection enables, by the Mail rule, and what each does.
struct ActivityVerbTarget: Equatable {
    let enabled: Set<ActivityPaneVerb>
    let selectionIds: Set<String>
    let perform: @MainActor (ActivityPaneVerb) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool { lhs.enabled == rhs.enabled && lhs.selectionIds == rhs.selectionIds }
}

/// What View › Activity ▸ reads from the focused Activity pane: its grouping and whether archived rows show.
struct ActivityViewTarget: Equatable {
    let grouping: ActivityPane.Grouping
    let showsArchived: Bool
    let setGrouping: @MainActor (ActivityPane.Grouping) -> Void
    let setShowsArchived: @MainActor (Bool) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool { lhs.grouping == rhs.grouping && lhs.showsArchived == rhs.showsArchived }
}

extension FocusedValues {
    @Entry var activityVerbs: ActivityVerbTarget?
    @Entry var activityView: ActivityViewTarget?
}

extension ActivityPaneView {
    // MARK: - Reading

    /// A run row drawn for the first time reads its tree; the last run row of a project pages in its next runs.
    func rowAppeared(_ row: ActivityMonitorRow) async {
        guard row.kind == .run, let library = library(for: row.libraryId) else { return }
        if let threadId = row.runThreadId { await library.activityStore.loadRunTree(threadId: threadId) }
        if row.runRowID == library.activityStore.runs.last?.id { await library.activityStore.loadMoreRuns(library: library) }
    }

    func library(for id: UUID?) -> LibraryManager.LibraryReference? {
        guard let id else { return nil }
        return libraries.first { $0.id == id }
    }

    /// Changes whenever the open projects, their live executions or their `refreshToken` change (#5431).
    var refreshKey: String {
        libraries.map { "\($0.id):\($0.workflowExecutionStore.executions.count):\($0.activityStore.refreshToken)" }
            .joined(separator: "|")
    }

    func refreshAll() async {
        for library in libraries {
            await library.activityStore.rebuildRuns(
                activeExecutions: Array(library.workflowExecutionStore.executions.values), library: library)
            await library.activityStore.loadRunsForToday(library: library)
        }
    }

    func readArchivedIfShown() async {
        for library in libraries { await library.activityStore.refreshArchivedJobs() }
    }

    // MARK: - The menu bar's targets

    /// The one selected row's Stop / Read Again, for Project › Activity (`FocusedActivityRunButtons`).
    var selectedRunTarget: ActivityRunMenuTarget? {
        let picked = rows(selection)
        return picked.count == 1 ? picked.first.map(runMenuTarget(for:)) : nil
    }

    var verbTarget: ActivityVerbTarget {
        let picked = rows(selection)
        return ActivityVerbTarget(
            enabled: Set(ActivityPaneVerb.allCases.filter { $0.isEnabled(for: picked) }),
            selectionIds: selection,
            perform: { verb in perform(verb, on: picked) }
        )
    }

    func runMenuTarget(for row: ActivityMonitorRow) -> ActivityRunMenuTarget {
        .make(rowId: row.id, rowName: row.name, canStop: ActivityPaneVerb.stop.allows(row),
              jobId: row.jobId, runThreadId: row.runThreadId, readAgainLabel: row.readAgainLabel,
              store: library(for: row.libraryId)?.activityStore, report: { notice = $0 })
    }

    // MARK: - Verbs

    /// The row's one button.
    func press(_ button: ActivityPaneButton, on row: ActivityMonitorRow) {
        switch button {
        case .verb(let verb): perform(verb, on: [row])
        case .settings: Self.openSettings()
        }
    }

    /// A verb on a selection, by the Mail rule: applied to the rows that allow it, the rest skipped and counted.
    func perform(_ verb: ActivityPaneVerb, on rows: [ActivityMonitorRow]) {
        if verb == .delete { requestDelete(rows); return }
        let (targets, skipped) = verb.split(rows)
        Task {
            if verb == .archive || verb == .putBack {
                let outcome = await archive(verb, targets)
                notice = ActivityPaneVerb.outcome(verb, done: outcome.done, skipped: skipped + outcome.skipped)
                return
            }
            var done = 0
            for row in targets {
                done += await act(verb, on: row) ? 1 : 0  // not `for … where await`: a where clause cannot await
            }
            notice = ActivityPaneVerb.outcome(verb, done: done, skipped: skipped + targets.count - done)
        }
    }

    /// Pause, Continue, Stop and Retry on one row through its job's audited actions; true when the engine took it.
    private func act(_ verb: ActivityPaneVerb, on row: ActivityMonitorRow) async -> Bool {
        if verb == .stop {
            guard let jobId = row.jobId, let store = library(for: row.libraryId)?.activityStore else { return false }
            return await ActivityRunMenuTarget.stopJob(jobId: jobId, runThreadId: row.runThreadId, store: store) == nil
        }
        guard let jobId = verb == .retry ? row.retryJobId : row.jobId,
              let store = library(for: row.libraryId)?.activityStore else { return false }
        switch verb {
        case .pause: return await store.setJobPaused(jobId: jobId, paused: true, runThreadId: row.runThreadId) == nil
        case .resume: return await store.setJobPaused(jobId: jobId, paused: false, runThreadId: row.runThreadId) == nil
        case .retry: return await store.retryJob(jobId: jobId, runThreadId: row.runThreadId) == nil
        case .stop, .archive, .putBack, .delete: return false
        }
    }

    /// Delete: one confirmation when a running row is among them (Stop then Delete), else at once. The whole selection
    /// goes on, so the rows Delete does not apply to are counted as skipped either way.
    func requestDelete(_ rows: [ActivityMonitorRow]) {
        let (targets, _) = ActivityPaneVerb.delete.split(rows)
        guard !targets.isEmpty else { return }
        if ActivityPaneVerb.deleteNeedsConfirmation(targets) {
            confirmingDelete = rows
        } else {
            Task { await delete(rows, stopRunning: false) }
        }
    }

    /// The ONE delete (#6583), routed per row's own project: jobs of their own through the audited `job.delete` (Stop then
    /// Delete when confirmed), one step on the window's stack so Edit › Undo puts them back (`job.undelete`); workflow runs
    /// through the runs delete, stopped first when confirmed. A run's delete is not undoable in the engine.
    func delete(_ rows: [ActivityMonitorRow], stopRunning: Bool) async {
        let (targets, skippedByState) = ActivityPaneVerb.delete.split(rows)
        var deleted = 0, skipped = skippedByState
        let jobIdsByLibrary = Self.jobIdsByLibrary(targets)
        for library in libraries {
            let ids = Set(targets.map(\.id))
            let runRows = targets.filter { $0.kind == .run && $0.libraryId == library.id }
            let threadIds = library.activityStore.runs.filter { ids.contains($0.id) }.map(\.runId)
            if !threadIds.isEmpty {
                let outcome = await deleteRuns(threadIds, stopping: stopRunning ? runRows.filter { $0.phase.isLive } : [],
                                               store: library.activityStore)
                deleted += outcome.deletedIds.count
                skipped += outcome.skippedIds.count
            }
            if let jobIds = jobIdsByLibrary[library.id], !jobIds.isEmpty {
                let outcome = await library.activityStore.performUndoable(
                    "job.delete", ids: jobIds, stopRunning: stopRunning,
                    named: UndoableChange.named("Delete", count: jobIds.count, one: "Row", many: "Rows"),
                    actions: library.actionsService, steps: windowSteps)
                deleted += outcome.done
                skipped += outcome.skipped
            }
        }
        selection = []
        notice = ActivityPaneVerb.outcome(.delete, done: deleted, skipped: skipped)
    }

    /// The runs delete; Stop then Delete stops the running ones first (their job's Stop), then deletes again what the
    /// engine still held as running. ponytail: up to ten one-second retries while the stop settles; a `stop_running` on
    /// the runs delete would make it one call.
    private func deleteRuns(_ threadIds: [String], stopping running: [ActivityMonitorRow],
                            store: ActivityStore) async -> RunDeleteOutcome {
        for row in running {
            if let jobId = row.jobId { _ = await ActivityRunMenuTarget.stopJob(jobId: jobId, runThreadId: row.runThreadId, store: store) }
        }
        let first = await store.deleteRuns(threadIds: threadIds)
        var deleted = first.deletedIds, pending = first.skippedIds
        var tries = 0
        while !running.isEmpty, !pending.isEmpty, tries < 10 {
            try? await Task.sleep(for: .seconds(1))
            tries += 1
            let again = await store.deleteRuns(threadIds: pending)
            deleted += again.deletedIds
            pending = again.skippedIds
        }
        return RunDeleteOutcome(deletedIds: deleted, skippedIds: pending)
    }

    /// Archive and Put Back, one step on the window's stack each, so Edit › Undo reverses it: ended job rows through the
    /// audited `job.archive` / `job.unarchive`, ended runs through `workflow_run.archive` (nothing deleted); a run is put
    /// back by `job.unarchive` too, its id being its row's id in the engine's jobs.
    private func archive(_ verb: ActivityPaneVerb, _ rows: [ActivityMonitorRow]) async -> ActivityJobsOutcome {
        var total = ActivityJobsOutcome()
        let jobIdsByLibrary = Self.jobIdsByLibrary(rows)
        for library in libraries {
            let jobIds = jobIdsByLibrary[library.id] ?? []
            let runIds = rows.filter { $0.kind == .run && $0.libraryId == library.id }.compactMap(\.runThreadId)
            let calls = verb == .archive
                ? [("job.archive", jobIds), ("workflow_run.archive", runIds)]
                : [("job.unarchive", jobIds + runIds)]
            for (action, ids) in calls where !ids.isEmpty {
                let outcome = await library.activityStore.performUndoable(
                    action, ids: ids, named: UndoableChange.named(verb.title, count: ids.count, one: "Row", many: "Rows"),
                    actions: library.actionsService, steps: windowSteps)
                total.done += outcome.done
                total.skipped += outcome.skipped
            }
        }
        return total
    }

    /// "Archive Finished…": every ended job and every ended run listed in the pane's projects, after one confirmation.
    func archiveFinished() async {
        var skipped = 0
        for library in libraries {
            let store = library.activityStore
            skipped += await store.archiveJobs(ids: [], states: ["done", "failed", "cancelled"]).skippedIds.count
            let ended = store.runs.filter { ActivityRunStatus.finished.contains($0.status) }.map(\.runId)
            if !ended.isEmpty {
                skipped += await store.performUndoable(
                    "workflow_run.archive", ids: ended,
                    named: UndoableChange.named("Archive", count: ended.count, one: "Run", many: "Runs"),
                    actions: library.actionsService, steps: windowSteps).skipped
            }
        }
        selection = []
        notice = skipped > 0 ? "\(skipped) skipped" : nil
    }

    /// "Archive Failed": every project's failed runs and jobs (`job.clear_failed`, the archive mark).
    func archiveFailed() async {
        var outcome = ClearFailedOutcome()
        for library in libraries { outcome += await library.activityStore.clearFailed() }
        notice = outcome.notice
    }

    /// The job ids Delete sends to each project's jobs delete: the selected job rows' own ids (a kind's row keeps its
    /// `waiting:<kind>` id, which the engine reads as the whole group).
    static func jobIdsByLibrary(_ rows: [ActivityMonitorRow]) -> [UUID: [String]] {
        var out: [UUID: [String]] = [:]
        for row in rows where row.kind == .job {
            guard let libraryId = row.libraryId, let jobId = row.jobId else { continue }
            out[libraryId, default: []].append(jobId)
        }
        return out
    }

    /// A failed row's fix when it is a setting (a key, a provider, a model): the Settings window.
    static func openSettings() {
        #if os(macOS)
        NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
        #endif
    }
}
