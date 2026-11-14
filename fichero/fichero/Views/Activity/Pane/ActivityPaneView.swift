import SwiftUI

/// The Activity pane (#6441, `activity.pane.is-a-pane-kind`): ONE flat outline table of every run and job, a pane kind like
/// Items or Reader. It lives in a main window beside the Inspector (any pane switches to it from its head's kind menu, and
/// the sidebar's Activity shows it), and it is the Activity window's whole content (`activity.window.is-the-pane-plus-inspector`).
///
/// Rows: a run (or a job of its own) and, under its disclosure, its files (`activity.pane.one-outline-table`); flat, sorted
/// by state then start, no section rows; Group by Run or by File over the same rows (`activity.pane.group-by-run-or-by-file`);
/// one filter field (`activity.pane.history-kept-and-filterable`); the one column table and the one verb list
/// (`ActivityPane.Column`, `ActivityPaneVerb`); one status bar at its foot. The selected row's details are the Inspector's
/// (`activity.pane.inspector-shows-the-selected-row`), told through `onSelect`.
///
/// Updates arrive one row at a time: a run's tree is read when its row is first drawn and again when the change stream names
/// its run (`ActivityStore.applyActivityEvent`); nothing reloads the table.
struct ActivityPaneView: View {
    /// Whose work it shows: one project, or nil for every open project (the project then leads each row's name).
    let libraryId: UUID?
    /// A pane in a main window has a head with its kind switcher; the Activity window's one pane has the window's title.
    var showsHead = false
    /// What the pane remembers (grouping, filter, open rows, columns) is kept under this key, one per pane.
    var paneKey = "activity.window"
    /// A row to select when it is listed (Show in Activity).
    var reveal: ActivitySelection?
    /// The selected row, for the Inspector beside the pane; nil with none or several selected.
    var onSelect: (ActivityPaneSelection?) -> Void = { _ in }

    @Environment(LibraryManager.self) private var libraryManager
    @Environment(\.undoManager) var undoManager
    @State var selection: Set<ActivityMonitorRow.ID> = []
    /// The outcome of the last verb, said in the status bar ("Deleted 4 · 1 skipped").
    @State var notice: String?
    @State private var confirmingArchiveFinished = false
    /// Delete on running rows asks once: Stop then Delete.
    @State var confirmingDelete: [ActivityMonitorRow]?
    @State private var showArchived = false
    @AppStorage("activity.pane.prefs") private var prefsData = Data()

    var prefs: ActivityPanePrefs { ActivityPanePrefs.load(prefsData, key: paneKey) }

    func update(_ change: (inout ActivityPanePrefs) -> Void) {
        prefsData = ActivityPanePrefs.store(prefsData, key: paneKey, change: change)
    }

    // MARK: - Libraries and rows

    /// The pane's projects: its own, or every open one with the global one too.
    var libraries: [LibraryManager.LibraryReference] {
        if let libraryId { return libraryManager.getLibrary(id: libraryId).map { [$0] } ?? [] }
        var references = libraryManager.openLibraries
        if let global = libraryManager.globalLibrary, !references.contains(where: { $0.id == global.id }) {
            references.append(global)
        }
        return references
    }

    /// Every top-level row, live and ended (the history is kept in the same table), plus the archived ones when shown.
    var allRows: [ActivityMonitorRow] {
        let rows = libraries.flatMap { library in
            let store = library.activityStore
            return ActivityMonitorRow.group(
                libraryId: library.id, libraryName: library.displayName,
                isMac: library.id == libraryManager.globalLibrary?.id,
                runRows: store.runs.map { .run($0, tree: store.runTrees[$0.threadId ?? $0.runId]) },
                jobs: store.liveJobs + store.historyJobs
            ).rows
        }
        // A run seen as a job of its own as well is listed once, as the run.
        let runJobs = Set(rows.filter { $0.kind == .run }.compactMap(\.jobId))
        return rows.filter { $0.kind == .run || !runJobs.contains($0.jobId ?? "") } + archivedRows
    }

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

    /// What the table shows: the grouping over the filtered rows.
    var shownRows: [ActivityMonitorRow] {
        let filter = ActivityPaneFilter(prefs.filter)
        let grouped = prefs.grouping == .file ? ActivityPane.byFile(allRows) : ActivityPane.outline(allRows)
        return filter.apply(grouped)
    }

    var showsProject: Bool { Set(allRows.compactMap(\.projectName)).count > 1 }

    // MARK: - Body

    var body: some View {
        VStack(spacing: 0) {
            if showsHead { head; Divider() }
            filterField
            if libraries.isEmpty {
                Color.clear  // empty means blank (`activity.window.no-empty-prose`)
            } else if shownRows.isEmpty, !ActivityPaneFilter(prefs.filter).isEmpty {
                Text("No activity matches").foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .accessibilityIdentifier("activity.noMatch")
            } else {
                table
            }
            statusBar
        }
        .accessibilityIdentifier("activity.pane")
        .focusedSceneValue(\.activityRun, selectedRunTarget)
        .focusedSceneValue(\.activityVerbs, verbTarget)
        .onChange(of: selection) { _, _ in onSelect(selectedPick) }
        .onChange(of: shownRows.map(\.id)) { _, _ in onSelect(selectedPick); if selection.isEmpty { select(reveal) } }
        .onChange(of: reveal) { _, wanted in select(wanted) }
        .onAppear { select(reveal) }
        .task(id: showArchived) { await readArchivedIfShown() }
        .task(id: refreshKey) { await refreshAll() }
        .confirmationDialog("Archive every finished run?", isPresented: $confirmingArchiveFinished) {
            Button("Archive Finished") { Task { await archiveFinished() } }
        } message: {
            Text("Done, failed and stopped runs leave the list and are kept under Show Archived.")
        }
        .confirmationDialog(
            "Stop and delete \(confirmingDelete?.filter { $0.phase == .running }.count ?? 0) running?",
            isPresented: Binding(get: { confirmingDelete != nil }, set: { if !$0 { confirmingDelete = nil } })
        ) {
            Button("Stop and Delete", role: .destructive) {
                if let rows = confirmingDelete { Task { await delete(rows, stopRunning: true) } }
                confirmingDelete = nil
            }
        } message: {
            Text("What they have done so far is discarded. Undo puts them back.")
        }
    }

    /// Switch the grouping, keeping a selected file selected (`activity.pane.group-by-run-or-by-file`).
    private func group(by grouping: ActivityPane.Grouping) {
        let rows = grouping == .file ? ActivityPane.byFile(allRows) : ActivityPane.outline(allRows)
        let carried = ActivityPane.carry(selection, into: rows)
        update { $0.grouping = grouping }
        selection = carried
    }

    /// Select the row a Show in Activity asked for, once it is listed.
    private func select(_ wanted: ActivitySelection?) {
        guard let wanted else { return }
        let ids = Set(allRows.filter { $0.selection == wanted }.map(\.id))
        if !ids.isEmpty, ids != selection { selection = ids }
    }

    // MARK: - Head, filter, status bar

    private var head: some View {
        PaneHead(
            crumbs: [PaneCrumb(id: "activity", title: "Activity", icon: PaneSpec.Kind.activity.icon)],
            selector: {
                PaneKindSelector(
                    kindTitle: PaneSpec.Kind.activity.title, kindIcon: PaneSpec.Kind.activity.icon,
                    currentKind: .activity, lenses: ActivityPane.Grouping.allCases,
                    lensTitle: { (grouping: ActivityPane.Grouping) in "By \(grouping.title)" },
                    lensIcon: { (grouping: ActivityPane.Grouping) in grouping == .run ? "list.bullet.indent" : "doc.on.doc" },
                    lens: Binding(get: { prefs.grouping }, set: group(by:))
                )
            },
            controls: { EmptyView() },
            tools: { EmptyView() }
        )
    }

    private var filterField: some View {
        HStack(spacing: 8) {
            if !showsHead {
                // The window has no pane head: Group by sits beside the filter.
                Picker("Group by", selection: Binding(get: { prefs.grouping }, set: group(by:))) {
                    ForEach(ActivityPane.Grouping.allCases) { Text($0.title).tag($0) }
                }
                .pickerStyle(.segmented)
                .fixedSize()
                .accessibilityIdentifier("activity.groupBy")
            }
            TextField("Filter: model: Kraken state: failed", text: Binding(
                get: { prefs.filter }, set: { value in update { $0.filter = value } }))
                .textFieldStyle(.roundedBorder)
                .accessibilityIdentifier("activity.filter")
            Menu {
                Toggle("Show Archived", isOn: $showArchived)
                Button("Archive Finished…") { confirmingArchiveFinished = true }
                Button("Archive Failed") { Task { await archiveFailed() } }
            } label: {
                Label("More", systemImage: "ellipsis.circle").labelStyle(.iconOnly)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .accessibilityIdentifier("activity.more")
        }
        .padding(.horizontal, 10).padding(.vertical, 6)
    }

    private var statusBar: some View {
        Text([statusBarText, notice].compactMap { $0 }.joined(separator: " · "))
            .font(.caption).foregroundStyle(.secondary).monospacedDigit().lineLimit(1)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 12).padding(.vertical, 4)
            .background(.bar)
            .accessibilityIdentifier("activity.statusbar")
    }

    /// "3 running · 12 waiting · $3.20 today", Finder style, and "Automatic work paused" while it is.
    private var statusBarText: String {
        let rows = allRows
        let today = rows.filter { row in (row.started ?? row.ended).map { Calendar.current.isDateInToday($0) } ?? row.phase.isLive }
        let spent = today.compactMap(\.costUsd).reduce(0, +)
        let counts = ActivityTrail.statusBar(running: rows.filter { $0.phase == .running }.count,
                                             waiting: rows.filter { $0.phase == .waiting }.count,
                                             spentTodayUsd: spent > 0 ? spent : nil)
        let paused = libraries.contains { $0.activityStore.backgroundMode == .paused }
        return paused ? counts + " · Automatic work paused" : counts
    }
}

#Preview("An Activity pane") {
    ActivityPaneView(libraryId: nil)
        .environment(LibraryManager.shared)
        .frame(width: 720, height: 360)
}
