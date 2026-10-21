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

    /// EVERY open library, global included (Daniel #19: "show ALL libraries").
    private var libraries: [LibraryManager.LibraryReference] {
        var references = libraryManager.openLibraries
        if let global = libraryManager.globalLibrary,
           !references.contains(where: { $0.id == global.id }) {
            references.append(global)
        }
        return references
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
                            guard let id = row.jobId, let store = modeStore else { return [] }
                            return ActivityStageBar.segments(of: ActivityDetails.stageCards(of: store.runTrees[id]))
                        },
                        stopTarget: { runMenuTarget(for: $0) },
                        clearFailed: { Task { await clearFailed() } },
                        clearFinished: { confirmingClearFinished = true },
                        delete: { rows in Task { await deleteRuns(withIDs: Set(rows.map(\.id))) } }
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
        .confirmationDialog("Remove every finished run?", isPresented: $confirmingClearFinished) {
            Button("Clear Finished", role: .destructive) { Task { await clearFinished() } }
        } message: {
            Text("Completed, failed and stopped runs leave the list. Runs still going are kept.")
        }
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
    private var allRows: [ActivityMonitorRow] { groups.flatMap(\.rows) + historyRows }

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

    /// The ONE delete operation (#4960), routed per row's OWN library. Only
    /// run rows delete; a still-running run is SKIPPED by the engine, and the
    /// reader is told.
    private func deleteRuns(withIDs ids: Set<ActivityMonitorRow.ID>) async {
        var skippedCount = 0
        for library in libraries {
            let threadIds = library.activityStore.runs.filter { ids.contains($0.id) }.map(\.runId)
            guard !threadIds.isEmpty else { continue }
            let outcome = await library.activityStore.deleteRuns(threadIds: threadIds)
            skippedCount += outcome.skippedIds.count
        }
        openedID = nil
        notice = skippedCount > 0 ? "\(skippedCount) run\(skippedCount == 1 ? "" : "s") still running — not deleted." : nil
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

    /// "Clear Finished" (#5016): the same soft delete as Delete, for every ended run in every project.
    private func clearFinished() async {
        var skipped = 0
        for library in libraries {
            let outcome = await library.activityStore.deleteRuns(statuses: ActivityRunStatus.finishedEngineNames)
            skipped += outcome.skippedIds.count
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
