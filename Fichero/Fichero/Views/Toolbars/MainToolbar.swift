import SwiftUI

/// Main application toolbar with all controls
/// Matches DevonThink-style toolbar layout
struct MainToolbar: View {
    // View mode bindings
    @Binding var viewMode: ViewDisplayMode
    @Binding var layoutMode: LayoutMode
    @Binding var showSidebar: Bool

    // Item creation registry
    @ObservedObject var itemRegistry: ItemTypeRegistry

    // Search
    @Binding var searchText: String

    var body: some View {
        HStack(spacing: 12) {
            // Left side: Sidebar toggle and Add button
            HStack(spacing: 8) {
                // Sidebar toggle button
                Button(action: { showSidebar.toggle() }) {
                    Label("Toggle Sidebar", systemImage: "sidebar.left")
                        .labelStyle(.iconOnly)
                }
                .help("Toggle Sidebar")

                // Add item menu
                AddItemMenu(registry: itemRegistry, style: .button)
                    .help("Create new item")
            }

            Spacer()

            // Center: Search field
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(.secondary)
                TextField("Search", text: $searchText)
                    .textFieldStyle(.plain)
                    .frame(maxWidth: 300)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(Color(nsColor: .controlBackgroundColor))
            .cornerRadius(6)

            Spacer()

            // Right side: View controls
            HStack(spacing: 12) {
                // Layout mode picker (None/Standard/Widescreen)
                Picker("Layout", selection: $layoutMode) {
                    ForEach(LayoutMode.allCases) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                .frame(width: 200)
                .help("Layout mode")

                Divider()
                    .frame(height: 20)

                // View mode picker (Icon/List/Table/Map)
                Picker("View", selection: $viewMode) {
                    ForEach(ViewDisplayMode.allCases) { mode in
                        Label(mode.rawValue, systemImage: mode.icon)
                            .labelStyle(.iconOnly)
                            .tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                .help("View mode")
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }
}

/// View display modes (Icon/List/Table/Map)
/// Universal across all content types
enum ViewDisplayMode: String, CaseIterable, Identifiable {
    case icon = "Icon"
    case list = "List"
    case table = "Table"
    case map = "Map"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .icon: return "square.grid.2x2"
        case .list: return "list.bullet"
        case .table: return "tablecells"
        case .map: return "map"
        }
    }

    var description: String {
        switch self {
        case .icon: return "Grid of icons"
        case .list: return "Linear list"
        case .table: return "Table view"
        case .map: return "Visual map"
        }
    }
}

#Preview {
    @Previewable @State var viewMode: ViewDisplayMode = .icon
    @Previewable @State var layoutMode: LayoutMode = .standard
    @Previewable @State var showSidebar: Bool = true
    @Previewable @State var searchText: String = ""

    let registry = ItemTypeRegistry()

    MainToolbar(
        viewMode: $viewMode,
        layoutMode: $layoutMode,
        showSidebar: $showSidebar,
        itemRegistry: registry,
        searchText: $searchText
    )
    .frame(height: 44)
    .onAppear {
        registry.createFolder = { print("Create folder") }
        registry.createSearch = { print("Create search") }
    }
}
