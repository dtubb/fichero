import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "AIModelCatalog")

/// AI model catalog for discovering Hugging Face models
/// Features: search, filter by task, sort, pagination
struct AIModelCatalog: View {
    @State private var models: [HFModelInfo] = []
    @State private var tasks: [HFTaskCategory] = []
    @State private var selectedTask: HFTaskCategory?
    @State private var searchQuery: String = ""
    @State private var sortOrder: HFSortOrder = .downloads
    @State private var isLoading = false
    @State private var hasMore = false
    @State private var offset = 0

    @Binding var selectedModel: HFModelInfo?
    let onModelSelected: ((HFModelInfo) -> Void)?

    @Environment(ModelService.self) var modelService
    private let pageSize = 20

    init(selectedModel: Binding<HFModelInfo?> = .constant(nil), onModelSelected: ((HFModelInfo) -> Void)? = nil) {
        self._selectedModel = selectedModel
        self.onModelSelected = onModelSelected
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header with search and filters
            headerView

            Divider()

            // Task categories (horizontal tabs)
            taskTabsView

            Divider()

            // Model list
            if isLoading && models.isEmpty {
                loadingView
            } else if models.isEmpty {
                emptyStateView
            } else {
                modelListView
            }
        }
    }

    // MARK: - Header

    private var headerView: some View {
        HStack(spacing: 12) {
            // Search field
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(.secondary)
                TextField("Search models...", text: $searchQuery)
                    .textFieldStyle(.plain)
                    .onSubmit {
                        Task { await searchModels(reset: true) }
                    }
                if !searchQuery.isEmpty {
                    Button {
                        searchQuery = ""
                        Task { await searchModels(reset: true) }
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(8)
            .background(Color(platformColor: .controlBackgroundColor))
            .cornerRadius(8)

            // Sort picker
            Picker("Sort", selection: $sortOrder) {
                ForEach(HFSortOrder.allCases) { order in
                    Text(order.label).tag(order)
                }
            }
            .pickerStyle(.menu)
            .frame(width: 160)
            .onChange(of: sortOrder) { _, _ in
                Task { await searchModels(reset: true) }
            }
        }
        .padding()
    }

    // MARK: - Task Tabs

    private var taskTabsView: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                // "All" tab
                taskTab(nil, label: "All")

                // Popular tasks
                ForEach(HFTaskCategory.popularTasks) { task in
                    taskTab(task, label: task.label)
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
        }
    }

    private func taskTab(_ task: HFTaskCategory?, label: String) -> some View {
        let isSelected = (task == nil && selectedTask == nil) || (task?.id == selectedTask?.id)

        return Button {
            selectedTask = task
            Task { await searchModels(reset: true) }
        } label: {
            Text(label)
                .font(.subheadline)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(isSelected ? Color.accentColor : Color(platformColor: .controlBackgroundColor))
                .foregroundColor(isSelected ? .white : .primary)
                .cornerRadius(16)
        }
        .buttonStyle(.plain)
    }

    // MARK: - Model List

    private var modelListView: some View {
        List {
            ForEach(models) { model in
                ModelRowView(
                    model: model,
                    isSelected: selectedModel?.id == model.id,
                    onSelect: {
                        selectedModel = model
                        onModelSelected?(model)
                    }
                )
                .listRowInsets(EdgeInsets())
                .listRowSeparator(.hidden)
            }

            // Load more button
            if hasMore {
                Button {
                    Task { await loadMore() }
                } label: {
                    if isLoading {
                        ProgressView()
                            .scaleEffect(0.8)
                    } else {
                        Text("Load More")
                    }
                }
                .frame(maxWidth: .infinity)
                .padding()
                .listRowSeparator(.hidden)
            }
        }
        .listStyle(.plain)
    }

    // MARK: - States

    private var loadingView: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Loading models...")
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var emptyStateView: some View {
        VStack(spacing: 12) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
            Text("No models found")
                .font(.headline)
            Text("Try a different search or filter")
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Data Loading

    private func searchModels(reset: Bool) async {
        if reset {
            offset = 0
        }

        isLoading = true
        defer { isLoading = false }

        do {
            let response = try await modelService.searchHuggingFaceModels(
                task: selectedTask?.id,
                search: searchQuery.isEmpty ? nil : searchQuery,
                sort: sortOrder,
                limit: pageSize,
                offset: offset
            )

            if reset {
                models = response.models
            } else {
                models.append(contentsOf: response.models)
            }
            hasMore = response.hasMore
        } catch {
            logger.error("Search failed: \(String(describing: error))")
        }
    }

    private func loadMore() async {
        offset += pageSize
        await searchModels(reset: false)
    }
}

// MARK: - Model Row

struct ModelRowView: View {
    let model: HFModelInfo
    let isSelected: Bool
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            HStack(spacing: 12) {
                // Model info
                VStack(alignment: .leading, spacing: 4) {
                    // Model name
                    Text(model.shortName)
                        .font(.headline)
                        .lineLimit(1)

                    // Author
                    Text(model.author)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .lineLimit(1)

                    // Tags
                    HStack(spacing: 4) {
                        if let task = model.pipelineTag {
                            TagView(text: task, color: .blue)
                        }
                        if let library = model.libraryName {
                            TagView(text: library, color: .purple)
                        }
                    }
                }

                Spacer()

                // Stats
                VStack(alignment: .trailing, spacing: 4) {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.down.circle")
                            .foregroundColor(.secondary)
                        Text(model.formattedDownloads)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }

                    HStack(spacing: 4) {
                        Image(systemName: "heart")
                            .foregroundColor(.secondary)
                        Text("\(model.likes)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .padding(12)
            .background(isSelected ? Color.accentColor.opacity(0.1) : Color.clear)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Tag View

struct TagView: View {
    let text: String
    let color: Color

    var body: some View {
        Text(text)
            .font(.caption2)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.15))
            .foregroundColor(color)
            .cornerRadius(4)
    }
}

// MARK: - Preview

#Preview("AI Model Catalog") {
    AIModelCatalog()
        .frame(width: 500, height: 600)
}
