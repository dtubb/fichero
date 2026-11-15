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
    @State private var showsInspector = true
    /// The models of the sidebar's Models section (`activity.window.models-tree`), and what the sidebar has picked.
    @State private var models: [ActivityModelEntry] = []
    @State private var sidebarPick: String?
    /// The graphs fill the centre (decision 41); kept per window.
    @SceneStorage("activity.graphs.full") private var graphsFull = false

    @Environment(LibraryManager.self) private var libraryManager
    /// The window's step stack: Delete, Archive and Put Back are steps on it, so Edit › Undo takes them back.
    @Environment(WindowSteps.self) var windowSteps: WindowSteps?
    @State var selection: Set<ActivityMonitorRow.ID> = []
    /// A column header's sort; empty keeps the state-then-start order.
    @State var sortOrder: [KeyPathComparator<ActivityMonitorRow>] = []
    /// The outcome of the last verb, said in the status bar ("Deleted 4 · 1 skipped").
    @State var notice: String?
    @State private var confirmingArchiveFinished = false
    /// Delete on running rows asks once: Stop then Delete.
    @State var confirmingDelete: [ActivityMonitorRow]?
    @State var showArchived = false
    /// The kept export a row's Choose Folder… is choosing a folder for: the system panel is up while it is set.
    @State var choosingFolder: ActivityFolderChoice?
    /// The open projects' history summed, for the window's bottom panel (`activity.window.bottom-panel`).
    @State private var history = ActivityHistory()
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

    private var archivedRows: [ActivityMonitorRow] {
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
                content
                    .toolbar { ToolbarItem(placement: .navigation) { ActivityRunControlsButtons() } }
                    .inspector(isPresented: $showsInspector) {
                        windowInspector?()
                            .inspectorColumnWidth(min: 280, ideal: 380, max: 640)
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

    private var content: some View {
        // Built once per draw and handed down: the table, its menu targets and the selection all read this one list.
        let shown = shownRows
        return VStack(spacing: 0) {
            if showsHead { head; Divider() }
            if showsHead {
                rowsView(shown)
            } else if prefs.tab == .recipes && !graphsFull {
                // Recipes (decision 37): recipe › run › step with the rates that compare them, over the graphs.
                VSplitView {
                    ActivityRecipesView(libraries: libraries).frame(minHeight: 140)
                    graphs
                }
            } else if graphsFull {
                // The graphs made full size (`activity.graphs.own-pane`, decision 41): they fill the centre.
                graphs
            } else {
                // The window's centre: the rows over the graphs, the divider the person's to drag (decisions 34, 41); a main
                // window's pane keeps one status line instead.
                VSplitView {
                    rowsView(shown).frame(minHeight: 140)
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
        .fileImporter(isPresented: Binding(get: { choosingFolder != nil }, set: { if !$0 { choosingFolder = nil } }),
                      allowedContentTypes: [.folder]) { result in
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
    private func rowsView(_ shown: [ActivityMonitorRow]) -> some View {
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
    private var graphs: some View {
        ActivityBottomPanel(tab: prefs.tab, history: history, rows: allRows, isFull: graphsFull,
                            toggleFull: { graphsFull.toggle() })
    }

    /// Show in Activity on a page: by File, its file row selected (`activity.pane.commands-through-the-table`).
    private func showFiles(_ documentIds: [String]?) {
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
    private func group(by grouping: ActivityPane.Grouping) {
        show(ActivityPane.Tab.of(grouping))
    }

    /// A tab: its grouping and its columns; the selected rows listed in both stay selected.
    func show(_ tab: ActivityPane.Tab) {
        let rows = tab.grouping == .file ? ActivityPane.byFile(allRows) : ActivityPane.outline(allRows)
        let carried = ActivityPane.carry(selection, into: rows)
        update { $0.tab = tab; $0.grouping = tab.grouping }
        selection = carried
    }

    private var inspectorToggle: some View {
        Button { showsInspector.toggle() } label: { Label("Inspector", systemImage: "sidebar.trailing") }
            .help(showsInspector ? "Hide the Inspector" : "Show the Inspector")
    }

    /// The Activity window's sidebar (`activity.window.sidebar`, decision 32): the items as a source list; choosing one is
    /// choosing what the centre lists and its columns. Each says how many of its rows need the person.
    var sidebar: some View {
        List(selection: Binding(get: { sidebarPick ?? "tab:\(prefs.tab.rawValue)" }, set: pickInSidebar)) {
            Section("Activity") {
                ForEach(ActivityPane.Tab.sidebarWork) { tab in sidebarRow(tab) }
            }
            Section("Resources") {
                ForEach(ActivityPane.Tab.sidebarResources) { tab in sidebarRow(tab) }
            }
            // Models by where they run (decision 33): place › provider › model, each model's icon filled while loaded, a green
            // dot while it works, its memory beside it.
            if !models.isEmpty {
                Section("Models") {
                    ForEach(ActivityModelEntry.tree(models), id: \.place) { place in
                        DisclosureGroup {
                            ForEach(place.providers, id: \.name) { provider in
                                DisclosureGroup {
                                    ForEach(provider.models) { model in modelRow(model) }
                                } label: {
                                    Label(provider.name, systemImage: "building.2").tag("provider:\(provider.name)")
                                }
                            }
                        } label: {
                            Label(place.place.title, systemImage: place.place.icon)
                        }
                    }
                }
            }
            Section {
                sidebarRow(.archived)
            }
        }
        .listStyle(.sidebar)
        .navigationSplitViewColumnWidth(min: 180, ideal: 220, max: 300)
        .accessibilityIdentifier("activity.sidebar")
        .task(id: libraries.map(\.id)) { await readModelsOften() }
    }

    private func modelRow(_ model: ActivityModelEntry) -> some View {
        HStack(spacing: 6) {
            Image(systemName: model.symbol)
                .foregroundStyle(model.loaded ? AnyShapeStyle(.primary) : AnyShapeStyle(.secondary))
            Text(model.name).lineLimit(1)
            Spacer(minLength: 4)
            if model.active {
                Circle().fill(.green).frame(width: 7, height: 7)
                    .symbolEffect(.pulse)
                    .accessibilityLabel("Working")
            }
            Text(model.memoryWords).font(.caption).foregroundStyle(.secondary).monospacedDigit()
        }
        .help("\(model.provider) · \(model.loaded ? "loaded" : "not loaded")\(model.active ? " · working" : "") · "
              + "\(model.pagesToday) pages, \(model.callsToday) calls today · memory \(model.memoryWords)")
        .tag("model:\(model.id)")
        .accessibilityIdentifier("activity.sidebar.model.\(model.name)")
    }

    /// A sidebar pick: an item shows its rows; a model or a provider lists the rows that ran on it (the filter, by model).
    private func pickInSidebar(_ pick: String?) {
        guard let pick else { return }
        sidebarPick = pick
        if pick.hasPrefix("tab:"), let tab = ActivityPane.Tab(rawValue: String(pick.dropFirst(4))) {
            show(tab)
            update { $0.filter = "" }
        } else if pick.hasPrefix("model:"), let model = models.first(where: { "model:\($0.id)" == pick }) {
            show(.runs)
            update { $0.filter = "model: \(model.name)" }
        } else if pick.hasPrefix("provider:") {
            show(.runs)
            update { $0.filter = "model: \(pick.dropFirst(9))" }
        }
    }

    /// The models of the open projects, read every ten seconds while the window shows: loaded and working change often.
    private func readModelsOften() async {
        while !Task.isCancelled {
            var lists: [[ActivityModelEntry]] = []
            for library in libraries {
                if let one = try? await library.activityService.models() { lists.append(one) }
            }
            models = ActivityModelEntry.merged(lists)
            try? await Task.sleep(for: .seconds(10))
        }
    }

    private func sidebarRow(_ tab: ActivityPane.Tab) -> some View {
        let needsYou = tab == .runs ? ActivityPane.needsYouCount(allRows) : 0
        return Label(tab.title, systemImage: tab.icon)
            .badge(needsYou)
            .tag("tab:\(tab.rawValue)")
            .accessibilityIdentifier("activity.sidebar.\(tab.rawValue)")
    }

    /// Select the row a Show in Activity asked for, once it is listed.
    /// Select every row asked for that is listed (the launch alert's Choose…: the rows the quit stopped).
    private func selectAll(_ wanted: [ActivitySelection]?) {
        guard let wanted, !wanted.isEmpty else { return }
        let ids = ActivityPane.rowIds(for: wanted, in: allRows)
        guard !ids.isEmpty else { return }
        selection = ids
        onRevealed()
    }

    private func select(_ wanted: ActivitySelection?) {
        guard let wanted else { return }
        let ids = Set(allRows.filter { $0.selection == wanted }.map(\.id))
        guard !ids.isEmpty else { return }
        selection = ids
        onRevealed()
    }

    // MARK: - Head, filter, status bar

    private var head: some View {
        PaneHead(
            crumbs: [PaneCrumb(id: "activity", title: "Activity", icon: PaneSpec.Kind.activity.icon)],
            selector: {
                PaneKindSelector(
                    kindTitle: PaneSpec.Kind.activity.title, kindIcon: PaneSpec.Kind.activity.icon,
                    currentKind: .activity, lenses: ActivityPane.Tab.allCases,
                    lensTitle: { (tab: ActivityPane.Tab) in tab.title },
                    lensIcon: { (tab: ActivityPane.Tab) in tab.icon },
                    lens: Binding(get: { prefs.tab }, set: show)
                )
            },
            controls: { EmptyView() },
            tools: { EmptyView() }
        )
    }

    /// The window's history, read now and once a minute while the window shows (`GET /api/activity/history`).
    private func readHistoryEachMinute() async {
        guard !showsHead else { return }
        while !Task.isCancelled {
            var read: [ActivityHistory] = []
            for library in libraries {
                if let one = try? await library.activityService.history() { read.append(one) }
            }
            history = ActivityBottomPanel.merged(read)
            try? await Task.sleep(for: .seconds(60))
        }
    }

    /// The pane's one bottom bar, the app's (`activity.pane.bottom-bar-like-every-pane`, #6588): the Filter field with what the
    /// list shows in its menu, and the status figures. The columns are chosen from a column header's menu, their widths kept
    /// (`activity.pane.columns-from-the-header`, decision 35).
    private var bottomBar: some View {
        PaneFilterBar(placement: .bottom) {
            PaneFilterField(text: Binding(get: { prefs.filter }, set: { value in update { $0.filter = value } }),
                            prompt: "Filter: model: Kraken state: failed", accessibilityID: "activity.filter") {
                Toggle("Show Archived", isOn: $showArchived)
                Divider()
                Button("Failed") { update { $0.filter = "state: failed" } }
                Button("Today") { update { $0.filter = "date: today" } }
                Button("Started Automatically") { update { $0.filter = "started by: automatic" } }
            }
            .frame(maxWidth: 360)
            Spacer(minLength: 8)
            // The window's figures are its bottom panel's; the bar keeps the notice there, the whole line in a main window's pane.
            Text((showsHead ? [statusBarText, notice] : [notice]).compactMap { $0 }.joined(separator: " · "))
                .font(.caption).foregroundStyle(.secondary).monospacedDigit().lineLimit(1)
                .accessibilityIdentifier("activity.statusbar")
            if showsHead { moreMenu }
        }
    }

    /// The More menu: Show Archived, Archive Finished… and Archive Failed (`activity.window.toolbar-verbs`), the window's
    /// toolbar's, and the bottom bar's in a main window's pane.
    private var moreMenu: some View {
        Menu {
            Toggle("Show Archived", isOn: $showArchived)
            Button("Archive Finished…") { confirmingArchiveFinished = true }
            Button("Archive Failed") { Task { await archiveFailed() } }
        } label: {
            Label("More", systemImage: "ellipsis.circle")
        }
        .help("Show Archived, Archive Finished…, Archive Failed")
        .accessibilityIdentifier("activity.more")
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

/// A row's Choose Folder…: the project and the kept export the panel chooses a folder for.
struct ActivityFolderChoice: Equatable {
    let libraryId: UUID?
    let exportId: String
}
