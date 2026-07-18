import OSLog
import SwiftUI
import UniformTypeIdentifiers

/// Action picker view for the workflow inspector - allows dragging actions onto canvas
struct ActionPickerView: View {
    @Environment(ActionStore.self) private var actionStore
    @State private var searchText = ""
    @State private var selectedCategory: String = "all"

    private let logger = Logger(subsystem: "app.fichero.fichero", category: "ActionPickerView")

    var body: some View {
        VStack(spacing: 0) {
            // Search bar
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField("Search actions...", text: $searchText)
                    .textFieldStyle(.plain)
                if !searchText.isEmpty {
                    Button {
                        searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(8)
            .background(.background)

            Divider()

            // Category tabs
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    CategoryTab(title: "All", isSelected: selectedCategory == "all") {
                        selectedCategory = "all"
                    }
                    CategoryTab(title: "Recent", isSelected: selectedCategory == "recent") {
                        selectedCategory = "recent"
                    }

                    ForEach(actionStore.categories, id: \.self) { category in
                        CategoryTab(
                            title: category.capitalized,
                            isSelected: selectedCategory == category
                        ) {
                            selectedCategory = category
                        }
                    }
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
            }
            .background(.bar)

            Divider()

            // Actions grid
            ScrollView {
                LazyVGrid(columns: [GridItem(.flexible())], spacing: 8) {
                    ForEach(filteredActions) { action in
                        DraggableActionCard(action: action)
                    }
                }
                .padding(8)
            }
        }
        .task {
            await actionStore.loadCategories()
            await actionStore.loadActions()
            await actionStore.loadRecentActions()
        }
    }

    private var filteredActions: [ActionItem] {
        var result: [ActionItem]

        switch selectedCategory {
        case "all":
            result = actionStore.actions
        case "recent":
            result = actionStore.recentActions
        default:
            result = actionStore.actions.filter { $0.category == selectedCategory }
        }

        if !searchText.isEmpty {
            let query = searchText.lowercased()
            result = result.filter {
                $0.name.lowercased().contains(query) ||
                    $0.description.lowercased().contains(query)
            }
        }

        return result
    }
}

// MARK: - Category Tab

struct CategoryTab: View {
    let title: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.caption)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(isSelected ? Color.accentColor : Color.secondary.opacity(0.2))
                .foregroundStyle(isSelected ? .white : .primary)
                .cornerRadius(12)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Draggable Action Card

struct DraggableActionCard: View {
    let action: ActionItem
    @Environment(ActionStore.self) private var actionStore
    @State private var isDragging = false

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: action.icon)
                .font(.title3)
                .foregroundStyle(Color.accentColor)
                .frame(width: 28)

            VStack(alignment: .leading, spacing: 2) {
                Text(action.name)
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .lineLimit(1)

                if !action.description.isEmpty {
                    Text(action.description)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }

            Spacer()

            Image(systemName: "line.3.horizontal")
                .foregroundStyle(.tertiary)
                .font(.caption)
        }
        .padding(10)
        .background(isDragging ? Color.accentColor.opacity(0.1) : Color.secondary.opacity(0.1))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isDragging ? Color.accentColor : Color.clear, lineWidth: 2)
        )
        .onDrag {
            isDragging = true
            // Record usage when dragged
            Task { @MainActor in
                await actionStore.recordUse(action.id)
            }
            return NSItemProvider(object: ActionDragData(action: action))
        }
        .onChange(of: isDragging) { _, _ in
            // Reset dragging state after a delay
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(0.5))
                isDragging = false
            }
        }
    }
}

// MARK: - Action Drag Data

final class ActionDragData: NSObject, NSItemProviderWriting, NSItemProviderReading, @unchecked Sendable {
    let action: ActionItem

    required init(action: ActionItem) {
        self.action = action
        super.init()
    }

    // MARK: - NSItemProviderWriting

    static var writableTypeIdentifiersForItemProvider: [String] {
        [UTType.actionDragData.identifier]
    }

    func loadData(
        withTypeIdentifier typeIdentifier: String,
        forItemProviderCompletionHandler completionHandler: @escaping (Data?, Error?) -> Void
    ) -> Progress? {
        let encoder = JSONEncoder()
        do {
            let data = try encoder.encode(action)
            completionHandler(data, nil)
        } catch {
            completionHandler(nil, error)
        }
        return nil
    }

    // MARK: - NSItemProviderReading

    static var readableTypeIdentifiersForItemProvider: [String] {
        [UTType.actionDragData.identifier]
    }

    static func object(withItemProviderData data: Data, typeIdentifier: String) throws -> ActionDragData {
        let decoder = JSONDecoder()
        let action = try decoder.decode(ActionItem.self, from: data)
        return ActionDragData(action: action)
    }
}

// MARK: - UTType Extension

extension UTType {
    static let actionDragData = UTType(exportedAs: "com.fichero.action-drag-data")
}

// MARK: - Compact Action Picker (for inspector sidebar)

struct CompactActionPicker: View {
    @Environment(ActionStore.self) private var actionStore
    @State private var searchText = ""
    @State private var expandedCategories: Set<String> = ["transcription", "extraction"]

    var body: some View {
        VStack(spacing: 0) {
            // Search
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                    .font(.caption)
                TextField("Search...", text: $searchText)
                    .textFieldStyle(.plain)
                    .font(.caption)
            }
            .padding(6)
            .background(.quaternary)
            .cornerRadius(6)
            .padding(8)

            // Categorized actions
            List {
                ForEach(groupedActions.keys.sorted(), id: \.self) { category in
                    DisclosureGroup(isExpanded: Binding(
                        get: { expandedCategories.contains(category) },
                        set: { isExpanded in
                            if isExpanded {
                                expandedCategories.insert(category)
                            } else {
                                expandedCategories.remove(category)
                            }
                        }
                    )) {
                        ForEach(groupedActions[category] ?? []) { action in
                            CompactActionRow(action: action)
                        }
                    } label: {
                        HStack {
                            Image(systemName: categoryIcon(category))
                                .foregroundStyle(.secondary)
                            Text(category.capitalized)
                                .font(.caption)
                                .fontWeight(.medium)
                        }
                    }
                }
            }
            .listStyle(.plain)
        }
        .task {
            await actionStore.loadActions()
        }
    }

    private var groupedActions: [String: [ActionItem]] {
        var filtered = actionStore.actions
        if !searchText.isEmpty {
            let query = searchText.lowercased()
            filtered = filtered.filter {
                $0.name.lowercased().contains(query) ||
                    $0.description.lowercased().contains(query)
            }
        }

        return Dictionary(grouping: filtered) { $0.category }
    }

    private func categoryIcon(_ category: String) -> String {
        switch category.lowercased() {
        case "transcription": return "waveform"
        case "extraction": return "doc.text.viewfinder"
        case "transformation": return "arrow.triangle.2.circlepath"
        case "analysis": return "chart.bar"
        case "generation": return "text.bubble"
        case "utility": return "wrench"
        default: return "square.stack.3d.up"
        }
    }
}

struct CompactActionRow: View {
    let action: ActionItem

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: action.icon)
                .font(.caption)
                .foregroundStyle(Color.accentColor)
                .frame(width: 16)

            Text(action.name)
                .font(.caption)
                .lineLimit(1)

            Spacer()
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
        .onDrag {
            NSItemProvider(object: ActionDragData(action: action))
        }
    }
}

#Preview {
    ActionPickerView()
        .environment(ActionStore(service: ActionsService()))
        .frame(width: 300, height: 500)
}
