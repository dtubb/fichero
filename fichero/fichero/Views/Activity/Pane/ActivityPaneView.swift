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
    /// The documents whose file row to select, by File (Show in Activity on a page): the first one listed.
    var revealFiles: [String]?
    /// Rows to select together once listed (the launch alert's Choose…).
    var revealAll: [ActivitySelection]?
    /// The selected row, for the Inspector beside the pane; nil with none or several selected.
    var onSelect: (ActivityPaneSelection?) -> Void = { _ in }
    /// A Show in Activity was answered (its row selected): the asker clears it, so a later refresh does not select it again.
    var onRevealed: () -> Void = {}
    /// The Activity window's Inspector, the third column (decision 38): the pane lays out sidebar › centre › Inspector itself,
    /// so the Inspector sits beside the centre, not around the split view. Nil in a main window's pane.
    var windowInspector: (() -> AnyView)?
    @State var showsInspector = true
    /// The models of the sidebar's Models section (`activity.window.models-tree`), and what the sidebar has picked.
    @State var models: [ActivityModelEntry] = []
    @State var sidebarPick: String?
    /// The graphs fill the centre (decision 41); kept per window.
    @SceneStorage("activity.graphs.full") var graphsFull = false

    @Environment(LibraryManager.self) var libraryManager
    /// The window's step stack: Delete, Archive and Put Back are steps on it, so Edit › Undo takes them back.
    @Environment(WindowSteps.self) var windowSteps: WindowSteps?
    @State var selection: Set<ActivityMonitorRow.ID> = []
    /// A column header's sort; empty keeps the state-then-start order.
    @State var sortOrder: [KeyPathComparator<ActivityMonitorRow>] = []
    /// The outcome of the last verb, said in the status bar ("Deleted 4 · 1 skipped").
    @State var notice: String?
    @State var confirmingArchiveFinished = false
    /// Delete on running rows asks once: Stop then Delete.
    @State var confirmingDelete: [ActivityMonitorRow]?
    @State var showArchived = false
    /// The kept export a row's Choose Folder… is choosing a folder for. Kept apart from the panel's own flag: the panel
    /// clears its binding before its completion runs, which would lose the export the chosen folder is for.
    @State var choosingFolder: ActivityFolderChoice?
    /// The system folder panel is up.
    @State var isChoosingFolder = false
    /// The open projects' history summed, for the window's bottom panel (`activity.window.bottom-panel`).
    @State var history = ActivityHistoryFigures()
    @AppStorage("activity.pane.prefs") var prefsData = Data()

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
            let jobs = store.liveJobs + store.historyJobs
            return ActivityPane.withRunFailures(ActivityPane.withQueuedFiles(ActivityMonitorRow.group(
                libraryId: library.id, libraryName: library.displayName,
                isMac: library.id == libraryManager.globalLibrary?.id,
                runRows: store.runs.map { .run($0, tree: store.runTrees[$0.threadId ?? $0.runId]) },
                jobs: jobs
            ).rows, queued: store.queuedItems), jobs: jobs)
        }
        // A run seen as a job of its own as well is listed once, as the run.
        let runJobs = Set(rows.filter { $0.kind == .run }.compactMap(\.jobId))
        // The Archived item lists the archived rows and only those (`activity.window.sidebar`).
        if prefs.tab == .archived { return archivedRows }
        return rows.filter { $0.kind == .run || !runJobs.contains($0.jobId ?? "") } + archivedRows
    }

    /// Archived rows are read while Show Archived is on or the Archived item is chosen.
    var listsArchived: Bool { showArchived || prefs.tab == .archived }

    var archivedRows: [ActivityMonitorRow] {
        guard listsArchived else { return [] }
        return libraries.flatMap { library in
            library.activityStore.archivedRuns.map { run in
                var row = ActivityMonitorRow.run(run, tree: nil)
                row.isArchived = true
                return row
            } + library.activityStore.archivedJobs.map { job in
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
        return filter.apply(ActivityPane.sorted(grouped, by: sortOrder))
    }

    var showsProject: Bool { Set(allRows.compactMap(\.projectName)).count > 1 }

    // MARK: - Body

    var body: some View {
        if showsHead {
            content
        } else {
            // The Activity window: sidebar › centre › Inspector (decisions 32, 38). Xcode's run controls lead the centre's
            // toolbar, right of the sidebar as in a main window (decision 30); the Inspector toggle at the far end.
            NavigationSplitView {
                sidebar
            } detail: {
                // Every column's size range is the fixed one of `ActivityPaneView+WindowLayout.swift`, never its
                // content's (#6661): sizes that did not fit the window together looped its constraints passes.
                content
                    .frame(minWidth: Self.centreMinWidth, maxWidth: .infinity,
                           minHeight: Self.centreMinHeight, maxHeight: .infinity)
                    .toolbar { ToolbarItem(placement: .navigation) { ActivityRunControlsBar() } }
                    .inspector(isPresented: $showsInspector) {
                        windowInspector?()
                            .frame(minWidth: 0, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity)
                            .inspectorColumnWidth(min: Self.inspectorWidths.lowerBound, ideal: Self.inspectorIdealWidth,
                                                  max: Self.inspectorWidths.upperBound)
                            // The Inspector column's own toolbar, at the window's trailing edge: More, then the toggle.
                            .toolbar {
                                ToolbarItem(placement: .primaryAction) { moreMenu }
                                ToolbarItem(placement: .primaryAction) { inspectorToggle }
                            }
                    }
                    .toolbar {
                        // With the Inspector closed its toggle and More stay reachable at the centre's trailing edge.
                        if !showsInspector {
                            ToolbarItem(placement: .primaryAction) { moreMenu }
                            ToolbarItem(placement: .primaryAction) { inspectorToggle }
                        }
                    }
            }
            // No title in the toolbar (the window keeps its name for the Window menu): its leading edge is the run controls'.
            .toolbar(removing: .title)
        }
    }

    var content: some View {
        // Built once per draw and handed down: the table, its menu targets and the selection all read this one list.
        let shown = shownRows
        return VStack(spacing: 0) {
            if showsHead { head; Divider() }
            if showsHead {
                rowsView(shown)
            } else if prefs.tab == .recipes && !graphsFull {
                // Recipes (decision 37): recipe › run › step with the rates that compare them, over the graphs.
                ActivityGraphsSplitStack {
                    ActivityRecipesView(libraries: libraries)
                } graphs: {
                    graphs
                }
            } else if graphsFull {
                // The graphs made full size (`activity.graphs.own-pane`, decision 41): they fill the centre.
                graphs
            } else {
                // The window's centre: the rows over the graphs, the divider the person's to drag (decisions 34, 41); a main
                // window's pane keeps one status line instead.
                ActivityGraphsSplitStack {
                    rowsView(shown)
                } graphs: {
                    graphs
                }
            }
            bottomBar
        }
        .accessibilityIdentifier("activity.pane")
        .onChange(of: selection) { _, _ in onSelect(selectedPick) }
        .onChange(of: shown.map(\.id)) { _, _ in onSelect(selectedPick); if selection.isEmpty { select(reveal) } }
        .onChange(of: reveal) { _, wanted in select(wanted) }
        .onChange(of: revealFiles) { _, wanted in showFiles(wanted) }
        .onChange(of: revealAll) { _, wanted in selectAll(wanted) }
        .onAppear { select(reveal); showFiles(revealFiles); selectAll(revealAll) }
        .task(id: listsArchived) { await readArchivedIfShown() }
        .task(id: refreshKey) { await refreshAll() }
        .task(id: libraries.map(\.id)) { await readHistoryEachMinute() }
        .fileImporter(isPresented: $isChoosingFolder, allowedContentTypes: [.folder]) { result in
            if case .success(let url) = result, let choice = choosingFolder { chose(url, for: choice) }
            choosingFolder = nil
        }
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

    /// The rows, or the one line that says there are none.
    @ViewBuilder
    func rowsView(_ shown: [ActivityMonitorRow]) -> some View {
        if libraries.isEmpty {
            Color.clear  // empty means blank (`activity.window.no-empty-prose`)
        } else if let line = ActivityPane.emptyLine(rowsShown: shown.count,
                                                    filterIsEmpty: ActivityPaneFilter(prefs.filter).isEmpty) {
            Text(line).foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .accessibilityIdentifier("activity.noMatch")
        } else {
            table(shown)
        }
    }

    /// The graphs pane: the sidebar item's graph and figures, full size or under the rows.
    var graphs: some View {
        ActivityBottomPanel(tab: prefs.tab, history: history, rows: allRows, isFull: graphsFull,
                            toggleFull: { graphsFull.toggle() })
    }

    /// Show in Activity on a page: by File, its file row selected (`activity.pane.commands-through-the-table`).
    func showFiles(_ documentIds: [String]?) {
        guard let documentIds, let id = ActivityPane.fileRowId(documentIds, in: ActivityPane.byFile(allRows)) else { return }
        update { $0.grouping = .file }
        selection = [id]
        onRevealed()
    }

    /// What View › Activity ▸ acts on: this pane's grouping and archived switch.
    var viewTarget: ActivityViewTarget {
        ActivityViewTarget(grouping: prefs.grouping, showsArchived: showArchived,
                           setGrouping: group(by:), setShowsArchived: { showArchived = $0 })
    }

    /// Switch the grouping, keeping a selected file selected (`activity.pane.group-by-run-or-by-file`).
    func group(by grouping: ActivityPane.Grouping) {
        show(ActivityPane.Tab.of(grouping))
    }

    /// A tab: its grouping and its columns; the selected rows listed in both stay selected.
    func show(_ tab: ActivityPane.Tab) {
        let rows = tab.grouping == .file ? ActivityPane.byFile(allRows) : ActivityPane.outline(allRows)
        let carried = ActivityPane.carry(selection, into: rows)
        update { $0.tab = tab; $0.grouping = tab.grouping }
        selection = carried
    }

    var inspectorToggle: some View {
        Button { showsInspector.toggle() } label: { Label("Inspector", systemImage: "sidebar.trailing") }
            .help(showsInspector ? "Hide the Inspector" : "Show the Inspector")
    }
}

#Preview("An Activity pane") {
    ActivityPaneView(libraryId: nil)
        .environment(LibraryManager.shared)
        .frame(width: 720, height: 360)
}
