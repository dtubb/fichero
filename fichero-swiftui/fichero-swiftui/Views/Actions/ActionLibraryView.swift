import SwiftUI
import OSLog

/// Action Library view for browsing and using reusable workflow actions
struct ActionLibraryView: View {
    @StateObject private var service = ActionsService()
    @State private var searchText = ""
    @State private var selectedCategory: String?
    @State private var selectedAction: ActionItem?
    @State private var showingCreateSheet = false

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

// MARK: - Action Row

struct ActionRowView: View {
    let action: ActionItem

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: action.icon)
                .font(.title2)
                .foregroundStyle(action.isBuiltin ? .blue : .orange)
                .frame(width: 32)

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(action.name)
                        .fontWeight(.medium)

                    if action.isBuiltin {
                        Text("Built-in")
                            .font(.caption2)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 2)
                            .background(.blue.opacity(0.2))
                            .cornerRadius(4)
                    }
                }

                Text(action.description)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)

                if !action.tags.isEmpty {
                    HStack(spacing: 4) {
                        ForEach(action.tags.prefix(3), id: \.self) { tag in
                            Text(tag)
                                .font(.caption2)
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                                .background(.quaternary)
                                .cornerRadius(3)
                        }
                    }
                }
            }

            Spacer()

            if action.useCount > 0 {
                VStack {
                    Text("\(action.useCount)")
                        .font(.caption)
                        .fontWeight(.medium)
                    Text("uses")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 4)
    }
}

// MARK: - Action Detail View

struct ActionDetailView: View {
    let action: ActionItem
    let service: ActionsService

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                HStack {
                    Image(systemName: action.icon)
                        .font(.system(size: 40))
                        .foregroundStyle(action.isBuiltin ? .blue : .orange)

                    VStack(alignment: .leading) {
                        Text(action.name)
                            .font(.title)
                            .fontWeight(.bold)

                        HStack {
                            Text(action.category.capitalized)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(.blue.opacity(0.2))
                                .cornerRadius(6)

                            if action.isBuiltin {
                                Text("Built-in")
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 4)
                                    .background(.green.opacity(0.2))
                                    .cornerRadius(6)
                            }

                            if action.isComposite {
                                Text("Composite")
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 4)
                                    .background(.purple.opacity(0.2))
                                    .cornerRadius(6)
                            }
                        }
                        .font(.caption)
                    }

                    Spacer()
                }

                // Description
                if !action.description.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Description")
                            .font(.headline)
                        Text(action.description)
                            .foregroundStyle(.secondary)
                    }
                }

                // Tags
                if !action.tags.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Tags")
                            .font(.headline)
                        FlowLayout(spacing: 8) {
                            ForEach(action.tags, id: \.self) { tag in
                                Text(tag)
                                    .font(.caption)
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 4)
                                    .background(.quaternary)
                                    .cornerRadius(6)
                            }
                        }
                    }
                }

                // Stats
                VStack(alignment: .leading, spacing: 8) {
                    Text("Statistics")
                        .font(.headline)

                    HStack(spacing: 24) {
                        StatItem(label: "Uses", value: "\(action.useCount)")
                        StatItem(label: "Author", value: action.author.isEmpty ? "Unknown" : action.author)
                    }
                }

                // Actions
                HStack(spacing: 12) {
                    Button {
                        Task {
                            await service.recordUse(actionId: action.id)
                        }
                    } label: {
                        Label("Use Action", systemImage: "play.fill")
                    }
                    .buttonStyle(.borderedProminent)

                    if !action.isBuiltin {
                        Button(role: .destructive) {
                            Task {
                                try? await service.deleteAction(id: action.id)
                            }
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                    }
                }
                .padding(.top)
            }
            .padding()
        }
        .navigationTitle(action.name)
    }
}

struct StatItem: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .fontWeight(.medium)
        }
    }
}

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

// MARK: - Flow Layout

struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = FlowResult(in: proposal.width ?? 0, subviews: subviews, spacing: spacing)
        return result.size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = FlowResult(in: bounds.width, subviews: subviews, spacing: spacing)
        for (index, subview) in subviews.enumerated() {
            subview.place(at: CGPoint(x: bounds.minX + result.positions[index].x,
                                      y: bounds.minY + result.positions[index].y),
                         proposal: .unspecified)
        }
    }

    struct FlowResult {
        var size: CGSize = .zero
        var positions: [CGPoint] = []

        init(in width: CGFloat, subviews: Subviews, spacing: CGFloat) {
            var xPos: CGFloat = 0
            var yPos: CGFloat = 0
            var lineHeight: CGFloat = 0

            for subview in subviews {
                let size = subview.sizeThatFits(.unspecified)

                if xPos + size.width > width && xPos > 0 {
                    xPos = 0
                    yPos += lineHeight + spacing
                    lineHeight = 0
                }

                positions.append(CGPoint(x: xPos, y: yPos))
                lineHeight = max(lineHeight, size.height)
                xPos += size.width + spacing
            }

            self.size = CGSize(width: width, height: yPos + lineHeight)
        }
    }
}

#Preview {
    ActionLibraryView()
}
