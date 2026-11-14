import SwiftUI

/// Root of the poppable "Activity" window (#2546 / B2): ONE table of every
/// run and job, across every open library (`activity.window.table`, #5415).
///
/// A row is a run, with a disclosure triangle into its steps and their pages
/// (`activity.window.expand`), read from the engine's run tree
/// (`GET /api/activity/jobs/{id}`, #5353). The columns are the measures that
/// matter (`activity.window.measures`): state with its reason, progress, start,
/// time, cost, errors and model, each sortable. Pause, Resume and Stop sit on
/// the row (`activity.pause.per-job`).
///
/// It replaced a flat list with nothing under a run. The library is on the
/// row unless rows are grouped by project (`activity.window.grouped-by-project`).
///
/// Updates arrive one row at a time: a run's tree is fetched when its row is
/// first drawn and again when the change stream names its run
/// (`ActivityStore.applyActivityEvent`); nothing reloads the table.
struct ActivityMonitorWindow: View {
    @Environment(LibraryManager.self) private var libraryManager
    @Environment(\.openWindow) private var openWindow
    @State private var selectionState = ActivityWindowSelectionState.shared
    /// The run opened over the list (`activity.window.open-a-run`).
    @State private var openedID: ActivityMonitorRow.ID?
    /// The outcome of the last Delete, Clear Failed, Pause or Stop: said
    /// plainly rather than silently (#4960).
    @State private var notice: String?
    /// The "Clear Finished…" confirmation (#5016).
    @State private var confirmingClearFinished = false
    /// Show Archived (`activity.pane.archive-old-runs`): the archived rows read once per toggle, listed greyed under History.
    @State private var showArchived = false

    /// EVERY open library, global included (Daniel #19: "show ALL libraries").
    private var libraries: [LibraryManager.LibraryReference] {
        var references = libraryManager.openLibraries
        if let global = libraryManager.globalLibrary,
           !references.contains(where: { $0.id == global.id }) {
            references.append(global)
        }
        return references
    }

    /// The engine's UP NEXT items of every open project that the list does not already show as a row.
    private var upNextLines: [ActivityPopoverSummary.UpNextLine] {
        ActivityPopoverSummary.upNextLines(libraries.compactMap { $0.activityStore.activitySummary },
                                           excluding: Set(windowGroups.upNext.map(\.id)),
                                           runName: { jobId in
                                               (windowGroups.now + windowGroups.upNext).first { $0.jobId == jobId }?
                                                   .displayName(showsProject: projectNames.count > 1)
                                           })
    }

    var body: some View {
        Group {
            if libraries.isEmpty {
                Color.clear  // empty means blank (`activity.window.no-empty-prose`)
            } else {
                if let selected = openedDetails {
                    // An opened run replaces the list; the back arrow returns to it (`activity.window.open-a-run`).
                    VStack(alignment: .leading, spacing: 0) {
                        Button { openedID = nil } label: { Label("Activity", systemImage: "chevron.left") }
                            .buttonStyle(.borderless)
                            .padding(10)
                            .accessibilityIdentifier("activity.back")
                        ActivityDetailsView(selection: selected.selection)
                            .libraryServiceEnvironment(selected.library)
                    }
                } else {
                    ActivityGroupsView(
                        groups: windowGroups, showsProject: projectNames.count > 1,
                        appeared: { await rowAppeared($0) },
                        perform: { button, row in perform(button, on: row) },
                        open: { openedID = $0.id },
                        stageSegments: { row in
                            let trees = ActivityStageBar.trees(libraries.map { ($0.id, $0.activityStore.runTrees) })
                            return ActivityStageBar.segments(for: row, trees: trees)
                        },
                        stopTarget: { runMenuTarget(for: $0) },
                        upNextLines: upNextLines,
                        clearFailed: { Task { await clearFailed() } },
                        clearFinished: { confirmingClearFinished = true },
                        delete: { rows in Task { await deleteRuns(withIDs: Set(rows.map(\.id))) } },
                        archive: { rows in Task { await archiveRows(rows) } },
                        putBack: { rows in Task { await putBack(rows) } },
                        showArchived: $showArchived
                    )
                }
            }
        }
        .navigationTitle("Activity")
        .frame(minWidth: 720, minHeight: 520)
        .accessibilityIdentifier("activity.window")
        .toolbar {
            // The one Start / Stop control (ruled 2026-10-09, `activity.mode.start-stop`): the mode is
            // the Mac's, so any open project's store sets it; one that polls the jobs read shows it, so
            // a change made in the main window or elsewhere reaches this button too (#5621).
            ToolbarItem {
                if let store = modeStore {
                    ActivityModeButton(store: store)
                }
            }
        }
        .task(id: showArchived) { await readArchivedIfShown() }
        .confirmationDialog("Archive every finished run?", isPresented: $confirmingClearFinished) {
            Button("Archive Finished") { Task { await clearFinished() } }
        } message: {
            Text("Completed, failed and stopped runs leave the list. Runs still going are kept.")
        }
        .safeAreaInset(edge: .bottom) { statusBar }
        .safeAreaInset(edge: .bottom) { footer }
        // The window owns the run-list load (Daniel, 2026-08-28).
        .task(id: refreshKey) { await refreshAll() }
    }

    @ViewBuilder
    private var footer: some View {
        // Per-library load failures + the last action's outcome (#4960 §2, #5431).
        VStack(spacing: 0) {
            ForEach(libraries.flatMap(\.activityStore.runLoadFailures), id: \.self) { message in
                ActivityFooterLine(message: message, onDismiss: nil)
            }
            if let notice {
                ActivityFooterLine(message: notice) { self.notice = nil }
            }
        }
    }

    // MARK: - Rows

    /// One group per open library, the global one titled as this Mac's own
    /// work: its runs (each with its tree when loaded) and its jobs of their own.
    private var groups: [ActivityMonitorRow.Group] {
        libraries.map { library in
            let store = library.activityStore
            return ActivityMonitorRow.group(
                libraryId: library.id,
                libraryName: library.displayName,
                isMac: library.id == libraryManager.globalLibrary?.id,
                runRows: store.runs.filter { !ActivityRunStatus.finished.contains($0.status) }
                    .map { .run($0, tree: store.runTrees[$0.threadId ?? $0.runId]) },
                jobs: store.liveJobs
            )
        }
    }

    /// What has ended: the runs that finished, stopped or failed and the jobs the engine put in History
    /// (`ActivityStore.historyJobs`), under their own heading, emptied by Clear Finished (`activity.window.history-group`).
    private var historyRows: [ActivityMonitorRow] {
        libraries.flatMap { library in
            ActivityMonitorRow.group(
                libraryId: library.id, libraryName: library.displayName,
                isMac: library.id == libraryManager.globalLibrary?.id,
                runRows: library.activityStore.runs.filter { ActivityRunStatus.finished.contains($0.status) }
                    .map { .run($0, tree: library.activityStore.runTrees[$0.threadId ?? $0.runId]) },
                jobs: library.activityStore.historyJobs
            ).rows
        }
    }

    /// Every top-level row, live and ended, as the one list's three groups (`activity.window.three-groups`).
    /// Every top-level row, live and ended, as the one list's three groups (`activity.window.three-groups`).
    private var allRows: [ActivityMonitorRow] { groups.flatMap(\.rows) + historyRows + archivedRows }

    /// Put Back: archived job rows are listed again, unchanged.
    private func putBack(_ rows: [ActivityMonitorRow]) async {
        let jobIdsByLibrary = Self.jobIdsByLibrary(rows)
        for library in libraries {
            if let jobIds = jobIdsByLibrary[library.id], !jobIds.isEmpty {
                await library.activityStore.unarchiveJobs(ids: jobIds)
            }
        }
    }

    private var windowGroups: ActivityWindowGroups { ActivityWindowGroups(rows: allRows) }

    /// The projects with work in the window: the project leads a row's name when there are several.
    private var projectNames: Set<String> { Set(allRows.compactMap(\.projectName)) }

    /// A run row drawn for the first time reads its tree; the last run row of
    /// a library pages in that library's next runs (#4960 infinite scroll).
    private func rowAppeared(_ row: ActivityMonitorRow) async {
        guard row.kind == .run, let library = library(for: row.libraryId) else { return }
        if let threadId = row.runThreadId {
            await library.activityStore.loadRunTree(threadId: threadId)
        }
        if row.runRowID == library.activityStore.runs.last?.id {
            await library.activityStore.loadMoreRuns(library: library)
        }
    }

    private func library(for id: UUID?) -> LibraryManager.LibraryReference? {
        guard let id else { return nil }
        return libraries.first { $0.id == id }
    }

    /// The opened run's details and its project.
    private var openedDetails: (selection: ActivitySelection, library: LibraryManager.LibraryReference)? {
        guard let id = openedID,
              let row = Self.find(id, in: allRows), let selection = row.selection,
              let library = library(for: row.libraryId) else { return nil }
        return (selection, library)
    }

    // MARK: - Actions

    /// Stop and Read Again for one row, shared by the row's own buttons, its context menu and the menu
    /// bar (#5652): each renders `ActivityStopMenuItem` / `ActivityReadAgainMenuItem` on this target.
    private func runMenuTarget(for id: ActivityMonitorRow.ID) -> ActivityRunMenuTarget? {
        Self.find(id, in: allRows).map(runMenuTarget(for:))
    }

    private func runMenuTarget(for row: ActivityMonitorRow) -> ActivityRunMenuTarget {
        .make(
            rowId: row.id, rowName: row.name, canStop: row.controls.contains(.stop),
            jobId: row.jobId, runThreadId: row.runThreadId, readAgainLabel: row.readAgainLabel,
            store: library(for: row.libraryId)?.activityStore, report: { notice = $0 }
        )
    }

    /// Pause, Resume or Stop one row's job through the audited job actions;
    /// the engine's answer is set on that row in place. Stop is the shared one (`runMenuTarget(for:)`).
    private func act(_ control: ActivityMonitorRow.Control, on row: ActivityMonitorRow) async {
        if control == .stop {
            runMenuTarget(for: row).stop()
            return
        }
        guard let jobId = control.isRetry ? row.retryJobId : row.jobId,
              let store = library(for: row.libraryId)?.activityStore else { return }
        let failure: String?
        switch control {
        case .pause: failure = await store.setJobPaused(jobId: jobId, paused: true, runThreadId: row.runThreadId)
        case .resume: failure = await store.setJobPaused(jobId: jobId, paused: false, runThreadId: row.runThreadId)
        case .stop: return
        case .retry, .carryOn: failure = await store.retryJob(jobId: jobId, runThreadId: row.runThreadId)
        }
        notice = failure.map { "Couldn't \(control.label.lowercased()) \(row.name): \($0)" }
    }

    /// A row's one button (`activity.window.one-button`): Pause, Resume and Retry act on its job; Show opens the run.
    private func perform(_ button: ActivityMonitorRow.OneButton, on row: ActivityMonitorRow) {
        switch button {
        case .pause: Task { await act(.pause, on: row) }
        case .resume: Task { await act(.resume, on: row) }
        case .retry: Task { await act(.retry, on: row) }
        case .show: openedID = row.id
        }
    }

    /// The ONE delete operation (#4960, #6583), routed per row's OWN library: run rows through the
    /// runs delete, job rows of their own (a recipe run, a download, a kind's group) through the jobs
    /// delete (`activity.window.delete-any-row`). A row still running is SKIPPED by the engine, and
    /// the reader is told.
    private func deleteRuns(withIDs ids: Set<ActivityMonitorRow.ID>) async {
        var skippedCount = 0
        let jobIdsByLibrary = Self.jobIdsByLibrary(allRows.filter { ids.contains($0.id) })
        for library in libraries {
            let threadIds = library.activityStore.runs.filter { ids.contains($0.id) }.map(\.runId)
            if !threadIds.isEmpty {
                skippedCount += await library.activityStore.deleteRuns(threadIds: threadIds).skippedIds.count
            }
            if let jobIds = jobIdsByLibrary[library.id], !jobIds.isEmpty {
                skippedCount += await library.activityStore.deleteJobs(ids: jobIds).skippedIds.count
            }
        }
        openedID = nil
        notice = skippedCount > 0 ? "\(skippedCount) item\(skippedCount == 1 ? "" : "s") still running — not deleted." : nil
    }

    /// The job ids Delete sends to each project's jobs delete: the selected job rows' own ids (a
    /// kind's row keeps its `waiting:<kind>` id, which the engine reads as the whole group).
    static func jobIdsByLibrary(_ rows: [ActivityMonitorRow]) -> [UUID: [String]] {
        var out: [UUID: [String]] = [:]
        for row in rows where row.kind == .job {
            guard let libraryId = row.libraryId, let jobId = row.jobId else { continue }
            out[libraryId, default: []].append(jobId)
        }
        return out
    }

    /// "Clear Failed" (#4960, #5634): every project's failed runs and failed
    /// jobs (`ActivityStore.clearFailed`), and the footer says what was
    /// cleared, or what could not be and why.
    private func clearFailed() async {
        var outcome = ClearFailedOutcome()
        for library in libraries {
            outcome += await library.activityStore.clearFailed()
        }
        notice = outcome.notice
    }

    /// "Archive Finished…" (#5016, #6583 `activity.pane.archive-old-runs`, `activity.pane.automatic-runs-easy-to-delete`): every
    /// ended run (its soft delete stands in for its archive) AND every ended job of its own (done, failed, stopped: the
    /// automatic ones too) in every project is ARCHIVED: hidden, kept, Put Back possible.
    private func clearFinished() async {
        var skipped = 0
        for library in libraries {
            let outcome = await library.activityStore.deleteRuns(statuses: ActivityRunStatus.finishedEngineNames)
            skipped += outcome.skippedIds.count
            skipped += await library.activityStore.archiveJobs(ids: [], states: ["done", "failed", "cancelled"]).skippedIds.count
        }
        openedID = nil
        notice = skipped > 0 ? "\(skipped) run\(skipped == 1 ? "" : "s") could not be cleared." : nil
    }

    /// The store the Start / Stop button reads: the first project's that polls
    /// the jobs read, else the first project's.
    private var modeStore: ActivityStore? {
        (libraries.first { $0.activityStore.pollsJobs } ?? libraries.first)?.activityStore
    }

    /// Changes whenever the set of open libraries, any library's live
    /// executions or its `refreshToken` change; the token is bumped by
    /// activity bursts and by the change stream's reconnect resync (#5431).
    private var refreshKey: String {
        libraries
            .map {
                "\($0.id):\($0.workflowExecutionStore.executions.count):\($0.activityStore.refreshToken)"
            }
            .joined(separator: "|")
    }

    /// Patch every open library's run list from its live executions and the
    /// runs table; each store owns its own merge.
    private func refreshAll() async {
        for library in libraries {
            await library.activityStore.rebuildRuns(
                activeExecutions: Array(library.workflowExecutionStore.executions.values),
                library: library
            )
            await library.activityStore.loadRunsForToday(library: library)
        }
    }
}

// MARK: - The one status bar (`activity.pane.less-is-more-table`, #6441)

extension ActivityMonitorWindow {
    /// "3 running · 12 waiting · $3.20 today", Finder style: the counts over every listed row, the spend over the rows that
    /// carry a cost (the day's total comes with the per-provider line later).
    private var statusBarText: String {
        let rows = allRows
        let spent = rows.compactMap(\.costUsd).reduce(0, +)
        return ActivityTrail.statusBar(running: rows.filter { $0.phase == .running }.count,
                                       waiting: rows.filter { $0.phase == .waiting }.count,
                                       spentTodayUsd: spent > 0 ? spent : nil)
    }

    private var statusBar: some View {
        Text(statusBarText)
            .font(.caption).foregroundStyle(.secondary).monospacedDigit()
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 12).padding(.vertical, 4)
            .background(.bar)
            .accessibilityIdentifier("activity.statusbar")
    }
}

// MARK: - Archive (`activity.pane.archive-old-runs`, #6583)

extension ActivityMonitorWindow {
    /// The archived rows, greyed, when Show Archived is on (`activity.pane.archive-old-runs`).
    private var archivedRows: [ActivityMonitorRow] {
        guard showArchived else { return [] }
        return libraries.flatMap { library in
            library.activityStore.archivedJobs.map { job in
                var row = ActivityMonitorRow.job(job, libraryId: library.id, projectName: library.displayName)
                row.isArchived = true
                return row
            }
        }
    }

    /// Archive (`activity.pane.archive-old-runs`): ended job rows through `job.archive`; ended run rows through the runs' soft
    /// delete, which stands in for their archive. What still goes is skipped and counted.
    private func archiveRows(_ rows: [ActivityMonitorRow]) async {
        var skipped = 0
        let jobIdsByLibrary = Self.jobIdsByLibrary(rows)
        for library in libraries {
            let threadIds = library.activityStore.runs.filter { run in rows.contains { $0.id == run.id } }.map(\.runId)
            if !threadIds.isEmpty {
                skipped += await library.activityStore.deleteRuns(threadIds: threadIds).skippedIds.count
            }
            if let jobIds = jobIdsByLibrary[library.id], !jobIds.isEmpty {
                skipped += await library.activityStore.archiveJobs(ids: jobIds).skippedIds.count
            }
        }
        notice = skipped > 0 ? "\(skipped) item\(skipped == 1 ? "" : "s") still running — not archived." : nil
    }

    /// Show Archived turned on: each project's archived rows are read once.
    private func readArchivedIfShown() async {
        guard showArchived else { return }
        for library in libraries { await library.activityStore.refreshArchivedJobs() }
    }
}
