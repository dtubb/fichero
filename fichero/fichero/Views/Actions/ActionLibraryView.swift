import AppKit
import OSLog
import SwiftUI

/// Action Library view for browsing and using reusable workflow actions
struct ActionLibraryView: View {
    @StateObject private var service = ActionsService()
    @State private var searchText = ""
    @State private var selectedCategory: String?
    @State private var selectedAction: ActionItem?
    @State private var showingCreateSheet = false
    @State private var actionMessage: String?

    var filteredActions: [ActionItem] {
        var result = service.actions

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
                ActionDetailView(action: action, service: service)
            } else {
                ContentUnavailableView(
                    "Select an Action",
                    systemImage: "square.stack.3d.up",
                    description: Text("Choose an action to view details")
                )
            }
        }
        .searchable(text: $searchText, prompt: "Search actions...")
        .task {
            await service.loadActions()
            await service.loadCategories()
        }
        .onChange(of: selectedCategory) { _, category in
            guard let category else { return }
            Task {
                _ = await service.loadActions(category: category)
            }
        }
        .alert(
            "Action Library",
            isPresented: Binding(
                get: { actionMessage != nil },
                set: { show in
                    if !show {
                        actionMessage = nil
                    }
                }
            )
        ) {
            Button("OK") { actionMessage = nil }
        } message: {
            Text(actionMessage ?? "")
        }
    }

    // MARK: - Sidebar

    private var sidebar: some View {
        List(selection: $selectedCategory) {
            Section("Categories") {
                Label("All Actions", systemImage: "square.stack.3d.up")
                    .tag(nil as String?)

                ForEach(service.categories, id: \.self) { category in
                    Label(category.capitalized, systemImage: iconForCategory(category))
                        .tag(category as String?)
                }
            }

            Section("Quick Access") {
                NavigationLink {
                    QuickAccessList(title: "Built-in", fetchActions: service.loadBuiltinActions)
                } label: {
                    Label("Built-in", systemImage: "building.columns")
                }

                NavigationLink {
                    QuickAccessList(title: "Custom", fetchActions: service.loadCustomActions)
                } label: {
                    Label("Custom", systemImage: "person")
                }

                NavigationLink {
                    QuickAccessList(title: "Popular", fetchActions: { await service.loadPopularActions() })
                } label: {
                    Label("Popular", systemImage: "star")
                }

                NavigationLink {
                    QuickAccessList(title: "Recent", fetchActions: { await service.loadRecentActions() })
                } label: {
                    Label("Recent", systemImage: "clock")
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
            CreateActionSheet(service: service)
        }
    }

    // MARK: - Actions List

    private var actionsList: some View {
        Group {
            if service.isLoading {
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
                        .contextMenu {
                            actionContextMenu(for: action)
                        }
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

    @ViewBuilder
    private func actionContextMenu(for action: ActionItem) -> some View {
        Button {
            Task {
                await service.recordUse(actionId: action.id)
                actionMessage = "Recorded use for \(action.name)."
            }
        } label: {
            Label("Use Action", systemImage: "play.fill")
        }

        Button {
            exportAction(action)
        } label: {
            Label("Export JSON", systemImage: "square.and.arrow.up")
        }

        Button {
            Task { await refreshAction(action) }
        } label: {
            Label("Refresh Details", systemImage: "arrow.clockwise")
        }

        if !action.isBuiltin {
            Button {
                Task { await updateActionMetadata(action) }
            } label: {
                Label("Save Metadata", systemImage: "checkmark.circle")
            }
        }

        Divider()

        Button {
            Task { await createActionFromNode(action) }
        } label: {
            Label("Create From Node", systemImage: "square.and.arrow.down.on.square")
        }

        Button {
            Task { await createCompositeAction(action) }
        } label: {
            Label("Create Composite", systemImage: "rectangle.connected.to.line.below")
        }

        if !action.isBuiltin {
            Divider()

            Button(role: .destructive) {
                Task {
                    try? await service.deleteAction(id: action.id)
                }
            } label: {
                Label("Delete", systemImage: "trash")
            }
        }
    }

    private func exportAction(_ action: ActionItem) {
        Task {
            do {
                let json = try await service.exportAction(id: action.id)
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(json, forType: .string)
                actionMessage = "Copied \(action.name) JSON to the clipboard."
            } catch {
                actionMessage = "Export failed: \(error.localizedDescription)"
            }
        }
    }

    private func refreshAction(_ action: ActionItem) async {
        do {
            selectedAction = try await service.getAction(id: action.id)
        } catch {
            actionMessage = "Refresh failed: \(error.localizedDescription)"
        }
    }

    private func updateActionMetadata(_ action: ActionItem) async {
        do {
            selectedAction = try await service.updateAction(
                id: action.id,
                request: UpdateActionRequest(
                    name: action.name,
                    description: action.description,
                    category: action.category,
                    tags: action.tags,
                    icon: action.icon
                )
            )
            actionMessage = "Saved \(action.name)."
        } catch {
            actionMessage = "Update failed: \(error.localizedDescription)"
        }
    }

    private func createActionFromNode(_ action: ActionItem) async {
        do {
            _ = try await service.createActionFromNode(
                CreateFromNodeActionRequest(
                    name: "\(action.name) Node Action",
                    node: action.nodeTemplate,
                    description: action.description,
                    category: action.category,
                    tags: action.tags
                )
            )
            actionMessage = "Created action from \(action.name)."
        } catch {
            actionMessage = "Create from node failed: \(error.localizedDescription)"
        }
    }

    private func createCompositeAction(_ action: ActionItem) async {
        do {
            _ = try await service.createCompositeAction(
                CreateCompositeActionRequest(
                    name: "\(action.name) Composite",
                    nodes: action.nodes,
                    edges: action.edges,
                    description: action.description,
                    category: action.category,
                    tags: action.tags
                )
            )
            actionMessage = "Created composite action from \(action.name)."
        } catch {
            actionMessage = "Create composite failed: \(error.localizedDescription)"
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
    let service: ActionsService
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
                            _ = try? await service.createAction(request)
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
}
