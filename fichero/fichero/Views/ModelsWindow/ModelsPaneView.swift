import SwiftUI

/// The Models and Cluster window's pane (`models.window.is-activitys-shape`, #6588): a source list (This Mac, Places, Work),
/// the one table and the Inspector, drawn from `ModelsWindowModel` over the engine's one models answer. It decides nothing:
/// the sections, the order, the badges and the Inspector's lines are the model's.
struct ModelsPaneView: View {
    @Environment(LibraryManager.self) private var libraryManager
    @State private var answer = ActivityModelsAnswer()
    @State private var item: ModelsWindowModel.Item? = .usableNow
    @State private var search = ""
    /// The verbs over the first open project's engine; nil until a project is open.
    @State private var store: ModelsWindowStore?
    @State private var selection: ActivityModelEntry.ID?
    @State private var showsInspector = true

    /// The derived lists are worked out when the answer or the item changes, not on each redraw.
    @State private var rows: [ActivityModelEntry] = []
    @State private var sidebarGroups = ModelsWindowModel.sidebar([])

    private var libraryIds: [UUID] {
        var ids = libraryManager.openLibraries.map(\.id)
        if let global = libraryManager.globalLibrary?.id, !ids.contains(global) { ids.append(global) }
        return ids
    }

    var body: some View {
        NavigationSplitView {
            sidebarList
                .alert("Delete this model?", isPresented: deleting, presenting: store?.pendingDelete) { row in
                    Button("Delete", role: .destructive) { Task { await store?.confirmDelete(row) } }
                    Button("Cancel", role: .cancel) { store?.pendingDelete = nil; store?.deleteWarning = nil }
                } message: { row in
                    Text(store?.deleteWarning ?? "\(row.name) is removed from this Mac.")
                }
        } detail: {
            content
                .inspector(isPresented: $showsInspector) { inspector.inspectorColumnWidth(min: 240, ideal: 300, max: 420) }
        }
        .toolbar {
            ToolbarItem {
                Button { Task { await store?.finder.searchOnline() } } label: { Label("Search Online", systemImage: "network") }
                    .disabled(store == nil || store?.finder.isSearching == true)
                    .accessibilityIdentifier("models.toolbar.searchOnline")
            }
            ToolbarItem {
                Button { showsInspector.toggle() } label: { Label("Inspector", systemImage: "sidebar.trailing") }
                    .accessibilityIdentifier("models.toolbar.inspector")
            }
        }
        .searchable(text: $search, prompt: "Search models")
        .task { await ModelsAnswerStore.shared.watch(libraryManager) }
        .task { await openStore() }
        .onChange(of: ModelsAnswerStore.shared.answers, initial: true) { refresh() }
        .onChange(of: item) { refresh() }
        .accessibilityIdentifier("models.pane")
    }

    // MARK: Sidebar

    private var sidebarList: some View {
        List(selection: $item) {
            Section { thisMacLine }
            ForEach(sidebarGroups, id: \.section) { group in
                Section(group.section.title) {
                    ForEach(group.entries, id: \.item) { entry in
                        Label(entry.title, systemImage: entry.icon)
                            .badge(entry.badge)
                            .tag(entry.item)
                            .accessibilityIdentifier("models.sidebar.\(entry.item.identifier)")
                    }
                }
            }
        }
        .navigationSplitViewColumnWidth(min: 190, ideal: 220)
    }

    /// This Mac's own line at the top of the sidebar, from `this_mac` of the answer.
    private var thisMacLine: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("This Mac").font(.headline)
            Text(answer.thisMac.map { "\($0.words)\($0.gpu.map { " · \($0)" } ?? "")" } ?? "—")
                .font(.caption).foregroundStyle(.secondary)
        }
        .accessibilityIdentifier("models.sidebar.mac")
    }

    // MARK: The table of the item

    /// The cards for a Models item, else the one table over the models answer.
    @ViewBuilder private var content: some View {
        if let list = item?.candidateList {
            if let store {
                VStack(spacing: 0) {
                    if let message = store.errorMessage { Text(message).foregroundStyle(.red).padding(6) }
                    ModelCandidatesListView(store: store, list: list, search: search)
                }
            } else {
                ContentUnavailableView("Open a project to find models for its steps.", systemImage: "magnifyingglass")
            }
        } else {
            table
        }
    }

    private var deleting: Binding<Bool> {
        Binding(get: { store?.pendingDelete != nil }, set: { if !$0 { store?.pendingDelete = nil } })
    }

    /// Takes the first open project's engine for the verbs and asks it for the candidates of its steps.
    private func openStore() async {
        guard let library = libraryManager.openLibraries.first else { return }
        let made = ModelsWindowStore(client: library.ficheroClient, finder: library.modelFinderStore)
        store = made
        await made.finder.load(library.recipeSetupStore.finderQuery(job: ModelFinderStore.readingJob))
    }

    // MARK: The one table

    private var table: some View {
        Table(rows, selection: $selection) {
            TableColumn("") { row in
                Image(systemName: row.symbol).foregroundStyle(row.lastFailed == nil ? Color.primary : Color.red)
            }
            .width(24)
            TableColumn("Name") { row in Text(row.name) }
            TableColumn("Where") { row in Text(row.provider) }
            TableColumn("Size") { row in Text(row.sizeWords) }
            TableColumn("Memory") { row in Text(row.memoryWords) }
            TableColumn("Fits here") { row in Text(row.fitsWords) }
            TableColumn("Account") { row in Text(row.accountWords) }
            TableColumn("Using now") { row in Text(row.usingNow.isEmpty ? "—" : row.usingNow.joined(separator: ", ")) }
            TableColumn("Last failed") { row in
                Text(row.lastFailed?.words ?? "—")
            }
            TableColumn("") { row in
                if let button = ModelsWindowModel.button(for: row), ModelsWindowStore.handles(button) {
                    Button(button) { Task { await store?.press(row) } }
                        .accessibilityIdentifier("models.row.\(row.id).button")
                }
            }
        }
        .overlay {
            if rows.isEmpty {
                ContentUnavailableView(ModelsAnswerStore.shared.failure ?? "Nothing here", systemImage: "cpu")
            }
        }
        .accessibilityIdentifier("models.table")
    }

    // MARK: Inspector

    private var inspector: some View {
        Form {
            if let row = ModelsWindowModel.selectedRow(selection, in: rows) {
                ForEach(ModelsWindowModel.inspectorLines(for: row), id: \.label) { line in
                    LabeledContent(line.label, value: line.value)
                }
            } else {
                Text("Select a model or a place.").foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .accessibilityIdentifier("models.inspector")
    }

    // MARK: Reading the one list

    /// Takes the shared store's answer and works out the sidebar and the rows once.
    private func refresh() {
        let fresh = ModelsAnswerStore.shared.answer(for: libraryIds)
        if fresh != answer { answer = fresh }
        sidebarGroups = ModelsWindowModel.sidebar(answer.models)
        rows = item.map { ModelsWindowModel.rows($0, in: answer.models) } ?? []
    }
}

#Preview("The Models and Cluster pane") {
    ModelsPaneView()
        .environment(LibraryManager.shared)
        .frame(width: 1100, height: 600)
}
