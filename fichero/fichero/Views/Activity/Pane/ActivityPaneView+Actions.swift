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
            var done = 0
            for row in targets where await act(verb, on: row) { done += 1 }
            if verb == .archive || verb == .putBack { await archive(verb, targets) }
            let failedHere = targets.count - done
            notice = ActivityPaneVerb.outcome(verb, done: verb == .archive || verb == .putBack ? targets.count : done,
                                              skipped: skipped + (verb == .archive || verb == .putBack ? 0 : failedHere))
        }
    }

    /// Pause, Continue, Stop and Retry on one row through its job's audited actions; true when the engine took it.
    private func act(_ verb: ActivityPaneVerb, on row: ActivityMonitorRow) async -> Bool {
        if verb == .stop {
            guard let jobId = row.jobId, let store = library(for: row.libraryId)?.activityStore else { return false }
            return await ActivityRunMenuTarget.stop(jobId: jobId, runThreadId: row.runThreadId, store: store) == nil
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

    /// Delete: one confirmation when a running row is among them (Stop then Delete), else at once.
    func requestDelete(_ rows: [ActivityMonitorRow]) {
        let (targets, _) = ActivityPaneVerb.delete.split(rows)
        guard !targets.isEmpty else { return }
        if ActivityPaneVerb.deleteNeedsConfirmation(targets) {
            confirmingDelete = targets
        } else {
            Task { await delete(rows, stopRunning: false) }
        }
    }

    /// The ONE delete (#6583), routed per row's own project: workflow runs through the runs delete, jobs of their own through
    /// the jobs delete (Stop then Delete when confirmed). Undo puts the jobs back as they were (`job.undelete`).
    func delete(_ rows: [ActivityMonitorRow], stopRunning: Bool) async {
        let (targets, skippedByState) = ActivityPaneVerb.delete.split(rows)
        var deleted = 0, skipped = skippedByState
        var undo: [(ActivityStore, [String])] = []
        let jobIdsByLibrary = Self.jobIdsByLibrary(targets)
        for library in libraries {
            let ids = Set(targets.map(\.id))
            let threadIds = library.activityStore.runs.filter { ids.contains($0.id) }.map(\.runId)
            if !threadIds.isEmpty {
                let outcome = await library.activityStore.deleteRuns(threadIds: threadIds)
                deleted += outcome.deletedIds.count
                skipped += outcome.skippedIds.count
            }
            if let jobIds = jobIdsByLibrary[library.id], !jobIds.isEmpty {
                let outcome = await library.activityStore.deleteJobs(ids: jobIds, stopRunning: stopRunning)
                deleted += outcome.deletedIds.count
                skipped += outcome.skippedIds.count
                if !outcome.deletedIds.isEmpty { undo.append((library.activityStore, outcome.deletedIds)) }
            }
        }
        selection = []
        notice = ActivityPaneVerb.outcome(.delete, done: deleted, skipped: skipped)
        registerUndo(undo, name: "Delete") { store, ids in _ = await store.undeleteJobs(ids: ids) }
    }

    /// Archive and Put Back: ended job rows through `job.archive` / `job.unarchive`; ended run rows through the runs' soft
    /// delete, which stands in for their archive. Undo reverses it.
    private func archive(_ verb: ActivityPaneVerb, _ rows: [ActivityMonitorRow]) async {
        var undo: [(ActivityStore, [String])] = []
        let jobIdsByLibrary = Self.jobIdsByLibrary(rows)
        for library in libraries {
            guard let jobIds = jobIdsByLibrary[library.id], !jobIds.isEmpty else {
                if verb == .archive {
                    let ids = Set(rows.map(\.id))
                    let threadIds = library.activityStore.runs.filter { ids.contains($0.id) }.map(\.runId)
                    if !threadIds.isEmpty { _ = await library.activityStore.deleteRuns(threadIds: threadIds) }
                }
                continue
            }
            if verb == .archive {
                let outcome = await library.activityStore.archiveJobs(ids: jobIds)
                if !outcome.deletedIds.isEmpty { undo.append((library.activityStore, outcome.deletedIds)) }
            } else {
                let back = await library.activityStore.unarchiveJobs(ids: jobIds)
                if !back.isEmpty { undo.append((library.activityStore, back)) }
            }
        }
        if verb == .archive {
            registerUndo(undo, name: "Archive") { store, ids in _ = await store.unarchiveJobs(ids: ids) }
        } else {
            registerUndo(undo, name: "Put Back") { store, ids in _ = await store.archiveJobs(ids: ids) }
        }
    }

    /// Edit › Undo for Delete and Archive (in session; the engine's actions are undoable).
    private func registerUndo(_ batches: [(ActivityStore, [String])], name: String,
                              reverse: @escaping @MainActor (ActivityStore, [String]) async -> Void) {
        guard let undoManager, !batches.isEmpty else { return }
        for (store, ids) in batches {
            undoManager.registerUndo(withTarget: store) { store in
                Task { @MainActor in
                    await reverse(store, ids)
                    store.refreshToken += 1
                }
            }
        }
        undoManager.setActionName(name)
    }

    /// "Archive Finished…": every ended run and job in the pane's projects, after one confirmation.
    func archiveFinished() async {
        var skipped = 0
        for library in libraries {
            skipped += await library.activityStore.deleteRuns(statuses: ActivityRunStatus.finishedEngineNames).skippedIds.count
            skipped += await library.activityStore.archiveJobs(ids: [], states: ["done", "failed", "cancelled"]).skippedIds.count
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
