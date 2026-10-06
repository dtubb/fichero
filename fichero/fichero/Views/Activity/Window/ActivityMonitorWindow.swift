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
    /// Multi-select (#4960 p3), separate from `selectionState`, which names
    /// the ONE run the detail window follows.
    @State private var selectedIDs: Set<ActivityMonitorRow.ID> = []
    @State private var sortOrder = ActivityMonitorRow.defaultSort
    /// The outcome of the last Delete, Clear Failed, Pause or Stop: said
    /// plainly rather than silently (#4960).
    @State private var notice: String?
    @AppStorage("activity.groupByProject") private var groupByProject = false

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
                ContentUnavailableView(
                    "No Library Open",
                    systemImage: "tray",
                    description: Text("Open a library to monitor its workflow activity.")
                )
            } else if groups.allSatisfy(\.rows.isEmpty) {
                ContentUnavailableView(
                    "No Runs Yet",
                    systemImage: "clock.arrow.circlepath",
                    description: Text("Workflow runs from every open library appear here.")
                )
            } else {
                VStack(spacing: 0) {
                    table
                    // The detail below the table (#5561): the selected row's details,
                    // the same view the ⓘ button and double-click open.
                    if let selected = selectedDetails {
                        Divider()
                        ActivityDetailsView(selection: selected.selection)
                            .libraryServiceEnvironment(selected.library)
                            .frame(minHeight: 220, idealHeight: 320)
                    }
                }
            }
        }
        .navigationTitle("Activity")
        .frame(minWidth: 720, minHeight: 520)
        .accessibilityIdentifier("activity.window")
        .toolbar {
            ToolbarItem {
                Toggle(isOn: $groupByProject) {
                    Label("Group by Project", systemImage: "square.stack.3d.up")
                }
                .help("Group the rows by project, with this Mac's own work as a group of its own")
            }
            ToolbarItem {
                Button("Clear Failed", role: .destructive) { Task { await clearFailed() } }
                    .disabled(!libraries.contains { $0.activityStore.runs.contains { $0.status == .failed } })
            }
        }
        .safeAreaInset(edge: .bottom) { footer }
        // The window owns the run-list load (Daniel, 2026-08-28).
        .task(id: refreshKey) { await refreshAll() }
    }

    private var table: some View {
        Table(of: ActivityMonitorRow.self, selection: $selectedIDs, sortOrder: $sortOrder) {
            TableColumn("Name", value: \.name) { row in
                ActivityNameCell(row: row, showsProject: !groupByProject)
                    .task(id: row.id) { await rowAppeared(row) }
            }
            .width(min: 180, ideal: 260)
            TableColumn("State", value: \.phaseKey) { row in ActivityStateCell(row: row) }
                .width(min: 120, ideal: 220)
            TableColumn("Progress", value: \.progressKey) { row in
                Text(row.progressText).monospacedDigit()
            }
            .width(min: 70, ideal: 150)
            TableColumn("Started", value: \.startedKey) { row in
                Text(row.started == nil ? "" : ActivityTimeText.absolute(row.started))
            }
            .width(min: 70, ideal: 110)
            TableColumn("Time", value: \.secondsKey) { row in ActivityElapsedCell(row: row) }
                .width(min: 50, ideal: 70)
            TableColumn("Cost", value: \.costKey) { row in Text(row.costText).monospacedDigit() }
                .width(min: 50, ideal: 70)
            TableColumn("Errors", value: \.errors) { row in
                Text(row.errorsText).monospacedDigit().foregroundStyle(.red)
            }
            .width(min: 40, ideal: 50)
            TableColumn("Model", value: \.modelKey) { row in Text(row.model ?? "").lineLimit(1) }
                .width(min: 60, ideal: 120)
            TableColumn("") { row in
                ActivityRowControls(
                    row: row,
                    perform: { control in Task { await act(control, on: row) } },
                    readAgain: { Task { await readPagesAgain(row) } },
                    showDetails: { showDetails(for: row) }
                )
            }
            .width(min: 70, ideal: 110)
        } rows: {
            if groupByProject {
                ForEach(sortedGroups) { group in
                    Section {
                        OutlineGroup(group.rows, children: \.children) { row in TableRow(row) }
                    } header: {
                        Text(group.title)
                            .accessibilityIdentifier(group.isMac ? "activity.group.mac" : "activity.group.\(group.id)")
                    }
                }
            } else {
                OutlineGroup(sortedRows, children: \.children) { row in TableRow(row) }
            }
        }
        .accessibilityIdentifier("activity.table")
        .contextMenu(forSelectionType: ActivityMonitorRow.ID.self) { ids in
            Button("Delete", role: .destructive) {
                Task { await deleteRuns(withIDs: ids) }
            }
        } primaryAction: { ids in
            guard ids.count == 1, let id = ids.first, let row = Self.find(id, in: sortedRows) else { return }
            showDetails(for: row)
        }
        #if os(macOS)
        .onDeleteCommand { Task { await deleteRuns(withIDs: selectedIDs) } }
        #endif
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
                runRows: store.runs.map { .run($0, tree: store.runTrees[$0.threadId ?? $0.runId]) },
                jobs: store.backgroundJobs
            )
        }
    }

    private var sortedRows: [ActivityMonitorRow] {
        ActivityMonitorRow.sorted(groups.flatMap(\.rows), using: sortOrder)
    }

    private var sortedGroups: [ActivityMonitorRow.Group] {
        groups.filter { !$0.rows.isEmpty }.map { group in
            var group = group
            group.rows = ActivityMonitorRow.sorted(group.rows, using: sortOrder)
            return group
        }
    }

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

    /// The one selected row's details and its project, for the detail below the table.
    private var selectedDetails: (selection: ActivitySelection, library: LibraryManager.LibraryReference)? {
        guard selectedIDs.count == 1, let id = selectedIDs.first,
              let row = Self.find(id, in: sortedRows), let selection = row.selection,
              let library = library(for: row.libraryId) else { return nil }
        return (selection, library)
    }

    private static func find(_ id: ActivityMonitorRow.ID, in rows: [ActivityMonitorRow]) -> ActivityMonitorRow? {
        for row in rows {
            if row.id == id { return row }
            if let found = find(id, in: row.children ?? []) { return found }
        }
        return nil
    }

    // MARK: - Actions

    /// Pause, Resume or Stop one row's job through the audited job actions;
    /// the engine's answer is set on that row in place.
    private func act(_ control: ActivityMonitorRow.Control, on row: ActivityMonitorRow) async {
        guard let jobId = row.jobId, let store = library(for: row.libraryId)?.activityStore else { return }
        let failure: String?
        switch control {
        case .pause: failure = await store.setJobPaused(jobId: jobId, paused: true, runThreadId: row.runThreadId)
        case .resume: failure = await store.setJobPaused(jobId: jobId, paused: false, runThreadId: row.runThreadId)
        case .stop: failure = await store.cancelJob(jobId: jobId, runThreadId: row.runThreadId)
        }
        notice = failure.map { "Couldn't \(control.label.lowercased()) \(row.name): \($0)" }
    }

    /// ⓘ on a row (#5560) and double-click: that row's own details (#5561), a
    /// step's or a page's too, not its run's. Selection is set FIRST because the
    /// details window reads what to show from the shared selection state.
    private func showDetails(for row: ActivityMonitorRow) {
        guard let selection = row.selection else { return }
        selectionState.select(selection)
        openWindow(id: ActivityWindowSelectionState.detailWindowID)
    }

    /// The run's offer at its end (#5555): one new run over the pages it did not do.
    private func readPagesAgain(_ row: ActivityMonitorRow) async {
        guard let threadId = row.runThreadId, let store = library(for: row.libraryId)?.activityStore else { return }
        let failure = await store.readPagesAgain(runThreadId: threadId)
        notice = failure.map { "Couldn't read the pages of \(row.name) again: \($0)" }
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
        selectedIDs.removeAll()
        notice = skippedCount > 0 ? "\(skippedCount) run\(skippedCount == 1 ? "" : "s") still running — not deleted." : nil
    }

    /// "Clear Failed" (#4960): the SAME delete operation with a status filter.
    private func clearFailed() async {
        var skippedCount = 0
        for library in libraries {
            let outcome = await library.activityStore.deleteRuns(statuses: ["failed"])
            skippedCount += outcome.skippedIds.count
        }
        notice = skippedCount > 0
            ? "\(skippedCount) run\(skippedCount == 1 ? "" : "s") could not be cleared."
            : nil
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
        }
    }
}

// MARK: - Cells (small, so the hierarchical Table type-checks quickly)

/// The row's name; a run's project before it when rows are not grouped.
private struct ActivityNameCell: View {
    let row: ActivityMonitorRow
    let showsProject: Bool

    var body: some View {
        HStack(spacing: 5) {
            // What kind of row it is (#5560): a run, a step, a page, a model load, training.
            Image(systemName: row.kindSymbol)
                .foregroundStyle(.secondary)
                .accessibilityLabel(row.kindWord)
            if showsProject, let project = row.projectName, !project.isEmpty {
                Text(project).foregroundStyle(.secondary)
                Text("·").foregroundStyle(.tertiary)
            }
            Text(row.name).lineLimit(1)
        }
        .accessibilityIdentifier("activity.row.\(row.jobId ?? row.id)")
    }
}

/// The state with its reason: a failed row says why, a waiting row what for.
private struct ActivityStateCell: View {
    let row: ActivityMonitorRow

    var body: some View {
        HStack(spacing: 5) {
            Image(systemName: row.phase.symbol)
                .foregroundStyle(color)
                .accessibilityHidden(true)
            Text(row.stateText)
                .lineLimit(1)
                .foregroundStyle(row.phase == .failed ? AnyShapeStyle(.red) : AnyShapeStyle(.primary))
        }
        .help([row.stateText, row.accountDetail].compactMap { $0 }.joined(separator: "\n"))
    }

    private var color: Color {
        switch row.phase {
        case .running: .blue
        case .waiting: .secondary
        case .paused, .cancelled: .orange
        case .failed: .red
        case .done: .green
        }
    }
}

/// How long it took; a run this window is watching ticks as a timer.
private struct ActivityElapsedCell: View {
    let row: ActivityMonitorRow

    var body: some View {
        if row.isLive, let started = row.started {
            Text(started, style: .timer).monospacedDigit()
        } else {
            Text(row.secondsText).monospacedDigit()
        }
    }
}

/// Pause or Resume, and Stop, on a row that is still working; on a finished
/// run with pages it did not do, its one offer ("Read the 3 pages that failed").
private struct ActivityRowControls: View {
    let row: ActivityMonitorRow
    let perform: (ActivityMonitorRow.Control) -> Void
    let readAgain: () -> Void
    let showDetails: () -> Void

    var body: some View {
        HStack(spacing: 4) {
            if let offer = row.readAgainLabel {
                Button(action: readAgain) {
                    Label(offer, systemImage: "arrow.clockwise")
                        .labelStyle(.iconOnly)
                }
                .buttonStyle(.borderless)
                .help(offer)
                .accessibilityLabel(offer)
                .accessibilityIdentifier("activity.row.\(row.jobId ?? row.id).readAgain")
            }
            ForEach(row.controls) { control in
                Button {
                    perform(control)
                } label: {
                    Label(control.label, systemImage: control.systemImage)
                        .labelStyle(.iconOnly)
                }
                .buttonStyle(.borderless)
                .help("\(control.label) \(row.name)")
                .accessibilityLabel("\(control.label) \(row.name)")
                .accessibilityIdentifier("activity.row.\(row.jobId ?? row.id).\(control == .stop ? "cancel" : control.rawValue)")
            }
            // Far right (#5560): the row's log and details, as double-click opens them.
            Spacer(minLength: 0)
            if row.opensDetails {
                Button(action: showDetails) {
                    Label("Show Details", systemImage: "info.circle")
                        .labelStyle(.iconOnly)
                }
                .buttonStyle(.borderless)
                .help("Show the log and details of \(row.name)")
                .accessibilityLabel("Show details of \(row.name)")
                .accessibilityIdentifier("activity.row.\(row.jobId ?? row.id).info")
            }
        }
    }
}

private struct ActivityFooterLine: View {
    let message: String
    let onDismiss: (() -> Void)?

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            Text(message)
                .font(.caption)
            Spacer(minLength: 8)
            if let onDismiss {
                Button("Dismiss", action: onDismiss)
                    .font(.caption)
                    .buttonStyle(.borderless)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(.regularMaterial)
    }
}
