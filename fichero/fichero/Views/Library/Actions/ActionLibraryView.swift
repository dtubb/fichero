import OSLog
import SwiftUI

/// Action Library view for browsing and using reusable workflow actions
struct ActionLibraryView: View {
    @Environment(ActionStore.self) private var actionStore
    @State private var searchText = ""
    @State private var selectedCategory: String?
    @State private var selectedAction: ActionItem?
    @State private var showingCreateSheet = false

    var filteredActions: [ActionItem] {
        var result = actionStore.actions

        if let category = selectedCategory {
            result = result.filter { $0.category == category }
        }

        if !searchText.isEmpty {
            result = result.filter {
                $0.name.localizedCaseInsensitiveContains(searchText) ||
                    $0.description.localizedCaseInsensitiveContains(searchText) ||
                    $0.tags.contains { $0.localizedCaseInsensitiveContains(searchText) }
            }
        }

        return result
    }

    var body: some View {
        NavigationSplitView {
            sidebar
                .navigationSplitViewColumnWidth(min: 180, ideal: 220)
        } content: {
            actionsList
                .navigationSplitViewColumnWidth(min: 250, ideal: 300)
        } detail: {
            if let action = selectedAction {
                ActionDetailView(action: action, service: actionStore.actionsService)
            } else {
                ContentUnavailableView(
                    "Select an Action",
                    systemImage: "square.stack.3d.up",
                    description: Text("Choose an action to view details")
                )
            }
        }
        // No per-view toolbar search: the toolbar search is global and always
        // searches files/documents (ContentView owns the single .searchable).
        // A second .searchable here is a duplicate com.apple.SwiftUI.search on
        // the same NSToolbar and crashes at launch (#3163). The list shows all.
        .task {
            await actionStore.loadActions()
            await actionStore.loadCategories()
        }
    }

    // MARK: - Sidebar

    private var sidebar: some View {
        List(selection: $selectedCategory) {
            Section("Categories") {
                Label("All Actions", systemImage: "square.stack.3d.up")
                    .tag(nil as String?)

                ForEach(actionStore.categories, id: \.self) { category in
                    Label(category.capitalized, systemImage: iconForCategory(category))
                        .tag(category as String?)
                }
            }

            Section("Quick Access") {
                NavigationLink {
                    QuickAccessList(title: "Built-in", fetchActions: actionStore.loadBuiltinActions)
                } label: {
                    Label("Built-in", systemImage: "building.columns")
                }

                NavigationLink {
                    QuickAccessList(title: "Custom", fetchActions: actionStore.loadCustomActions)
                } label: {
                    Label("Custom", systemImage: "person")
                }

                NavigationLink {
                    QuickAccessList(title: "Popular", fetchActions: { await actionStore.loadPopularActions() })
                } label: {
                    Label("Popular", systemImage: "star")
                }
            }
        }
        .listStyle(.sidebar)
        .navigationTitle("Library")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    showingCreateSheet = true
                } label: {
                    Image(systemName: "plus")
                }
                .help("Create new action")
            }
        }
        .sheet(isPresented: $showingCreateSheet) {
            CreateActionSheet(store: actionStore)
        }
    }

    // MARK: - Actions List

    private var actionsList: some View {
        Group {
            if actionStore.isLoading {
                ProgressView("Loading actions...")
            } else if filteredActions.isEmpty {
                ContentUnavailableView(
                    searchText.isEmpty ? "No Actions" : "No Results",
                    systemImage: "magnifyingglass",
                    description: Text(searchText.isEmpty ? "Create your first action" : "Try a different search")
                )
            } else {
                List(filteredActions, selection: $selectedAction) { action in
                    ActionRowView(action: action)
                        .tag(action)
                }
                .listStyle(.inset)
            }
        }
        .navigationTitle(selectedCategory?.capitalized ?? "All Actions")
    }

    private func iconForCategory(_ category: String) -> String {
        switch category.lowercased() {
        case "ai": return "brain"
        case "transform": return "arrow.triangle.2.circlepath"
        case "extract": return "doc.text.magnifyingglass"
        case "analyze": return "chart.bar"
        case "generate": return "sparkles"
        case "search": return "magnifyingglass"
        case "communicate": return "envelope"
        case "logic": return "arrow.triangle.branch"
        default: return "square.stack.3d.up"
        }
    }
}

// ActionRowView is defined in Views/Actions/ActionRowView.swift — do not duplicate

// ActionDetailView and StatItem are defined in Views/Actions/ActionDetailView.swift — do not duplicate

// MARK: - Quick Access List

struct QuickAccessList: View {
    let title: String
    let fetchActions: () async -> [ActionItem]

    @State private var actions: [ActionItem] = []
    @State private var isLoading = true

    var body: some View {
        Group {
            if isLoading {
                ProgressView()
            } else if actions.isEmpty {
                ContentUnavailableView("No \(title) Actions", systemImage: "tray")
            } else {
                List(actions) { action in
                    ActionRowView(action: action)
                }
            }
        }
        .navigationTitle(title)
        .task {
            actions = await fetchActions()
            isLoading = false
        }
    }
}

// MARK: - Create Action Sheet

struct CreateActionSheet: View {
    let store: ActionStore
    @Environment(\.dismiss) private var dismiss

    @State private var name = ""
    @State private var description = ""
    @State private var category = "custom"
    @State private var tags = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("Basic Info") {
                    TextField("Name", text: $name)
                    TextField("Description", text: $description, axis: .vertical)
                        .lineLimit(3...6)
                }

                Section("Classification") {
                    Picker("Category", selection: $category) {
                        Text("Custom").tag("custom")
                        Text("AI").tag("ai")
                        Text("Transform").tag("transform")
                        Text("Extract").tag("extract")
                        Text("Analyze").tag("analyze")
                        Text("Generate").tag("generate")
                        Text("Search").tag("search")
                        Text("Communicate").tag("communicate")
                        Text("Logic").tag("logic")
                    }

                    TextField("Tags (comma-separated)", text: $tags)
                }
            }
            .navigationTitle("New Action")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        Task {
                            let tagList = tags.split(separator: ",")
                                .map { String($0.trimmingCharacters(in: .whitespaces)) }
                            var request = CreateActionRequest(name: name)
                            request.description = description
                            request.category = category
                            request.tags = tagList
                            _ = try? await store.createAction(request)
                            dismiss()
                        }
                    }
                    .disabled(name.isEmpty)
                }
            }
        }
        .frame(minWidth: 400, minHeight: 300)
    }
}

// FlowLayout is defined in Views/Components/FlowLayout.swift — do not duplicate

#Preview {
    ActionLibraryView()
        .environment(ActionStore(service: ActionsService(client: .localhost)))
}
