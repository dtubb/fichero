import SwiftUI

/// The Models and Cluster window's pane (`models.window.is-activitys-shape`, #6588): a source list (This Mac, Places, Work),
/// the one table and the Inspector, drawn from `ModelsWindowModel` over the engine's one models answer. It decides nothing:
/// the sections, the order, the badges and the Inspector's lines are the model's.
struct ModelsPaneView: View {
    @Environment(LibraryManager.self) private var libraryManager
    @State private var answer = ActivityModelsAnswer()
    @State private var item: ModelsWindowModel.Item? = .thisMac
    @State private var selection: ActivityModelEntry.ID?
    @State private var showsInspector = true
    @State private var readFailed: String?

    private var rows: [ActivityModelEntry] {
        item.map { ModelsWindowModel.rows($0, in: answer.models) } ?? []
    }

    /// The open projects and the global one: the models answer is per project's engine connection.
    private var libraries: [LibraryManager.LibraryReference] {
        var references = libraryManager.openLibraries
        if let global = libraryManager.globalLibrary, !references.contains(where: { $0.id == global.id }) {
            references.append(global)
        }
        return references
    }

    var body: some View {
        NavigationSplitView {
            sidebar
        } detail: {
            table
                .inspector(isPresented: $showsInspector) { inspector.inspectorColumnWidth(min: 240, ideal: 300, max: 420) }
        }
        .toolbar {
            ToolbarItem {
                Button { showsInspector.toggle() } label: { Label("Inspector", systemImage: "sidebar.trailing") }
                    .accessibilityIdentifier("models.toolbar.inspector")
            }
        }
        .task { await readOften() }
        .accessibilityIdentifier("models.pane")
    }

    // MARK: Sidebar

    private var sidebar: some View {
        List(selection: $item) {
            Section { thisMacLine }
            ForEach(ModelsWindowModel.sidebar(answer.models), id: \.section) { group in
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
                Text([row.lastFailed?.words, ModelsWindowModel.button(for: row)].compactMap { $0 }.joined(separator: " · ")
                    .nilIfEmpty ?? "—")
            }
        }
        .overlay {
            if rows.isEmpty {
                ContentUnavailableView(readFailed ?? "Nothing here", systemImage: "cpu")
            }
        }
        .accessibilityIdentifier("models.table")
    }

    // MARK: Inspector

    private var inspector: some View {
        Form {
            if let row = rows.first(where: { $0.id == selection }) {
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

    /// The engine's models answer through the generated client, every ten seconds while the window shows.
    private func readOften() async {
        while !Task.isCancelled {
            var answers: [ActivityModelsAnswer] = []
            var failure: String?
            for library in libraries {
                do { answers.append(try await library.activityService.models()) } catch { failure = error.localizedDescription }
            }
            answer = ActivityModelsAnswer.merged(answers)
            readFailed = answers.isEmpty ? failure : nil
            try? await Task.sleep(for: .seconds(10))
        }
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}

#Preview("The Models and Cluster pane") {
    ModelsPaneView()
        .environment(LibraryManager.shared)
        .frame(width: 1100, height: 600)
}
