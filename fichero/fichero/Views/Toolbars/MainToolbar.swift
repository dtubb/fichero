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
                Button(
                    action: { showSidebar.toggle() },
                    label: {
                        Label("Toggle Sidebar", systemImage: "sidebar.left")
                            .labelStyle(.iconOnly)
                    }
                )
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
                Picker("View mode", selection: $viewMode) {
                    ForEach(ViewDisplayMode.allCases) { mode in
                        Label(mode.label, systemImage: mode.icon)
                            .labelStyle(.iconOnly)
                            .tag(mode)
                            .accessibilityLabel(mode.label + " — " + mode.description)
                    }
                }
                .pickerStyle(.segmented)
                .help("View mode — choose how documents are displayed")
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
    case realitykit = "RealityKit"
    case spatial = "Spatial"
    case workspace = "Workspace"

    var id: String { rawValue }

    /// Mail-style display label shown in pickers/menus. `table` → "Column"
    /// (#1613). `rawValue` deliberately stays "Table" so persisted per-folder
    /// modes and the XCUITest hooks (`viewMode-Table`) don't churn.
    var label: String {
        switch self {
        case .table: "Column"
        default: rawValue
        }
    }

    var icon: String {
        switch self {
        case .icon: "square.grid.2x2"
        case .list: "list.bullet"
        case .table: "tablecells"
        case .map: "map"
        case .realitykit: "cube.transparent"
        case .spatial: "square.3.layers.3d"
        case .workspace: "square.stack.3d.up"
        }
    }

    var description: String {
        switch self {
        case .icon: "Grid of icons"
        case .list: "Linear list"
        case .table: "Column view"
        case .map: "Visual map"
        case .realitykit: "Spatial 3D view"
        case .spatial: "Spatial collection view"
        case .workspace: "Workspace collection view"
        }
    }
}

// `.table` renders as the multi-column table view (`LibraryView.tableView`);
// its user-facing name is "Column" (Mail-style, #1613) while the enum case and
// rawValue stay `.table`/"Table".

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
    .frame(height: MiniToolbar<EmptyView>.standardHeight)
    .onAppear {
        registry.createFolder = { print("Create folder") }
        registry.createSearch = { print("Create search") }
    }
}
