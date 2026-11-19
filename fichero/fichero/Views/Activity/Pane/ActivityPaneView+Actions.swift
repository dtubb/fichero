import SwiftUI

/// The verbs the menu bar's Project › Activity reads from the focused Activity pane (`activity.pane.commands-through-the-table`):
/// which verbs the selection enables, by the Mail rule, and what each does.
struct ActivityVerbTarget: Equatable {
    let enabled: Set<ActivityPaneVerb>
    let selectionIds: Set<String>
    let perform: @MainActor (ActivityPaneVerb) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool { lhs.enabled == rhs.enabled && lhs.selectionIds == rhs.selectionIds }

    /// The verbs a selection enables, by the Mail rule: one is enabled when any selected row allows it.
    static func enabledVerbs(for rows: [ActivityMonitorRow]) -> Set<ActivityPaneVerb> {
        Set(ActivityPaneVerb.allCases.filter { $0.isEnabled(for: rows) })
    }
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
        // A queue row reads the files it works on, so its disclosure can show them (#6599).
        if row.kind == .job, ActivityStore.queuedKind(ofRowId: row.id) != nil, let library = library(for: row.libraryId) {
            await library.activityStore.loadQueuedItems(rowId: row.id)
            return
        }
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

    /// The one selected row's Stop, for Project › Activity (`FocusedActivityRunButtons`).
    func selectedRunTarget(in shown: [ActivityMonitorRow]) -> ActivityRunMenuTarget? {
        let picked = rows(selection, in: shown)
        return picked.count == 1 ? picked.first.map(runMenuTarget(for:)) : nil
    }

    func verbTarget(in shown: [ActivityMonitorRow]) -> ActivityVerbTarget {
        let picked = rows(selection, in: shown)
        return ActivityVerbTarget(
            enabled: ActivityVerbTarget.enabledVerbs(for: picked),
            selectionIds: selection,
            perform: { verb in perform(verb, on: picked) }
        )
    }

    func runMenuTarget(for row: ActivityMonitorRow) -> ActivityRunMenuTarget {
        .make(.init(rowId: row.id, rowName: row.name, canStop: ActivityPaneVerb.stop.allows(row),
                    jobId: row.jobId, runThreadId: row.runThreadId, readAgainLabel: row.readAgainLabel),
              store: library(for: row.libraryId)?.activityStore, report: { notice = $0 })
    }

    // MARK: - Verbs

    /// The row's one button.
    func press(_ button: ActivityPaneButton, on row: ActivityMonitorRow) {
        switch button {
        case .verb(let verb): perform(verb, on: [row])
        case .settings: Self.openSettings(control: row.failure?.settingsControl, appState: appState)
        case .chooseFolder(let export):
            choosingFolder = ActivityFolderChoice(libraryId: row.libraryId, exportId: export)
            isChoosingFolder = true
        case .showDetails: selection = [row.id]  // the Inspector shows the selected row's fix
        }
    }

    /// The folder the panel chose for a kept export: the export moves there and its paused row writes there.
    func chose(_ folder: URL, for choice: ActivityFolderChoice) {
        guard let store = library(for: choice.libraryId)?.keptExportStore else { return }
        Task {
            let moved = await store.chooseFolder(choice.exportId, folder: folder)
            notice = moved ? "Writing to \(folder.lastPathComponent)" : store.errorMessage
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
            var refusal: String?
            for row in targets {
                // not `for … where await`: a where clause cannot await
                if let error = await act(verb, on: row) { refusal = refusal ?? error } else { done += 1 }
            }
            // The engine's words when it refused, never a bare count (`runner.surface.one-row-one-alert`).
            notice = refusal ?? ActivityPaneVerb.outcome(verb, done: done, skipped: skipped + targets.count - done)
        }
    }

    /// Pause, Continue, Stop and Retry on one row through its job's audited actions; nil when the engine took it, else the
    /// engine's words for why not (or that the row has no job).
    private func act(_ verb: ActivityPaneVerb, on row: ActivityMonitorRow) async -> String? {
        let skipped = "This row has no job to act on."
        if verb == .stop {
            guard let jobId = row.jobId, let store = library(for: row.libraryId)?.activityStore else { return skipped }
            return await ActivityRunMenuTarget.stopJob(jobId: jobId, runThreadId: row.runThreadId, store: store)
        }
        guard let jobId = verb == .retry ? row.retryJobId : row.jobId,
              let store = library(for: row.libraryId)?.activityStore else { return skipped }
        switch verb {
        case .pause: return await store.setJobPaused(jobId: jobId, paused: true, runThreadId: row.runThreadId)
        case .resume: return await store.setJobPaused(jobId: jobId, paused: false, runThreadId: row.runThreadId)
        case .retry: return await store.retryJob(jobId: jobId, runThreadId: row.runThreadId)
        case .stop, .archive, .putBack, .delete: return skipped
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
            let running = stopRunning ? targets.filter { $0.kind == .run && $0.libraryId == library.id && $0.phase.isLive } : []
            let threadIds = library.activityStore.runs.filter { ids.contains($0.id) }.map(\.runId)
            let jobIds = jobIdsByLibrary[library.id] ?? []
            guard !threadIds.isEmpty || !jobIds.isEmpty else { continue }
            // Stop then Delete: the running runs are stopped first (their job's Stop), then deleted with the rest.
            for row in running {
                if let jobId = row.jobId {
                    _ = await ActivityRunMenuTarget.stopJob(jobId: jobId, runThreadId: row.runThreadId, store: library.activityStore)
                }
            }
            // One step per project for all its rows, runs and jobs together (#6599).
            let outcome = await library.activityStore.deleteAsOneStep(
                ids: (threadIds, jobIds), stopRunning: stopRunning, settling: !running.isEmpty,
                actions: library.actionsService, steps: windowSteps)
            deleted += outcome.done
            skipped += outcome.skipped
        }
        selection = []
        notice = ActivityPaneVerb.outcome(.delete, done: deleted, skipped: skipped)
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
        await archive(states: ["done", "failed", "cancelled"], runStatuses: ActivityRunStatus.finished)
    }

    /// "Archive Failed": every project's failed runs and jobs, one undoable step per project.
    func archiveFailed() async {
        await archive(states: ["failed"], runStatuses: [.failed])
    }

    /// Each project's ended jobs in `states` and its runs in `runStatuses` archived as ONE step (#6599); Undo puts them back.
    private func archive(states: [String], runStatuses: [ActivityRunStatus]) async {
        var archived = 0, skipped = 0
        for library in libraries {
            let store = library.activityStore
            let ended = store.runs.filter { runStatuses.contains($0.status) }.map(\.runId)
            let outcome = await store.archiveAsOneStep(states: states, threadIds: ended, actions: library.actionsService,
                                                       steps: windowSteps)
            archived += outcome.done
            skipped += outcome.skipped
        }
        selection = []
        notice = ActivityPaneVerb.outcome(.archive, done: archived, skipped: skipped)
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
    /// It lands on the control the failure names: `settings.ai.*` is the AI tab (`SettingsTab.holding`).
    static func openSettings(control: String? = nil, appState: AppState? = nil) {
        if let tab = SettingsTab.holding(control: control), let appState {
            appState.openSettings(tab: tab)
            return
        }
        #if os(macOS)
        NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
        #endif
    }
}
