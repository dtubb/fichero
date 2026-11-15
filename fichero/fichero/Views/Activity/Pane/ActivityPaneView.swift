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
    /// The selected row, for the Inspector beside the pane; nil with none or several selected.
    var onSelect: (ActivityPaneSelection?) -> Void = { _ in }
    /// A Show in Activity was answered (its row selected): the asker clears it, so a later refresh does not select it again.
    var onRevealed: () -> Void = {}

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
        // Built once per draw and handed down: the table, its menu targets and the selection all read this one list.
        let shown = shownRows
        VStack(spacing: 0) {
            if showsHead { head; Divider() }
            if libraries.isEmpty {
                Color.clear  // empty means blank (`activity.window.no-empty-prose`)
            } else if shown.isEmpty, !ActivityPaneFilter(prefs.filter).isEmpty {
                Text("No activity matches").foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .accessibilityIdentifier("activity.noMatch")
            } else {
                table(shown)
            }
            bottomBar
        }
        .accessibilityIdentifier("activity.pane")
        // The window has no pane head: its four tabs are the toolbar's (decision 23); a main window's pane has them in its
        // head's lens menu.
        .toolbar {
            if !showsHead {
                ToolbarItem(placement: .principal) { tabPicker }
                ToolbarItem(placement: .primaryAction) { moreMenu }
            }
        }
        .onChange(of: selection) { _, _ in onSelect(selectedPick) }
        .onChange(of: shown.map(\.id)) { _, _ in onSelect(selectedPick); if selection.isEmpty { select(reveal) } }
        .onChange(of: reveal) { _, wanted in select(wanted) }
        .onChange(of: revealFiles) { _, wanted in showFiles(wanted) }
        .onAppear { select(reveal); showFiles(revealFiles) }
        .task(id: showArchived) { await readArchivedIfShown() }
        .task(id: refreshKey) { await refreshAll() }
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

    /// The four tabs as one segmented control: the Activity window's toolbar holds it.
    private var tabPicker: some View {
        Picker("View", selection: Binding(get: { prefs.tab }, set: show)) {
            ForEach(ActivityPane.Tab.allCases) { Text($0.title).tag($0) }
        }
        .pickerStyle(.segmented)
        .fixedSize()
        .help("Runs, Files, Cost or Where: what the table lists and its columns")
        .accessibilityIdentifier("activity.tabs")
    }

    /// Select the row a Show in Activity asked for, once it is listed.
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

    /// The pane's one bottom bar, the app's (`activity.pane.bottom-bar-like-every-pane`, #6588): Metadata (the column toggles,
    /// the same as the header's menu), the Filter field with what the list shows in its menu, and the status figures.
    private var bottomBar: some View {
        PaneFilterBar(placement: .bottom) {
            PaneMetadataButton { columnToggles }
                .help("Which columns the table shows")
                .accessibilityIdentifier("activity.metadata")
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
            Text([statusBarText, notice].compactMap { $0 }.joined(separator: " · "))
                .font(.caption).foregroundStyle(.secondary).monospacedDigit().lineLimit(1)
                .accessibilityIdentifier("activity.statusbar")
            if showsHead { moreMenu }
        }
    }

    /// Each column of the tab, on or off: the header's menu, in the bar (`activity.pane.default-columns`).
    @ViewBuilder
    private var columnToggles: some View {
        ForEach(ActivityPane.Column.allCases.filter { $0 != .name && $0 != .source }, id: \.self) { column in
            Toggle(column.title, isOn: Binding(
                get: { prefs.columns(for: prefs.tab)[visibility: column.rawValue] != .hidden },
                set: { isOn in
                    update { prefs in
                        var columns = prefs.columns(for: prefs.tab)
                        columns[visibility: column.rawValue] = isOn ? .visible : .hidden
                        prefs.setColumns(columns, for: prefs.tab)
                    }
                }))
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
