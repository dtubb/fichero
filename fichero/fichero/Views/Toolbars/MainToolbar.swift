import SwiftUI

/// Main application toolbar with all controls
/// Matches DevonThink-style toolbar layout
struct MainToolbar: View {
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

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
                if horizontalSizeClass != .compact {
                    Button(
                        action: { showSidebar.toggle() },
                        label: {
                            Label("Toggle Sidebar", systemImage: "sidebar.left")
                                .labelStyle(.iconOnly)
                        }
                    )
                    .help("Toggle Sidebar")
                }

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
            .background(Color(platformColor: .controlBackgroundColor))
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
                    ForEach(ViewDisplayMode.selectableCases) { mode in
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
    // RETIRED 3D "Space" / Mind Palace alias. The RealityKit renderer was
    // removed (3D rooms superseded by the live 2D spatial library view). The
    // case is retained ONLY so persisted/@SceneStorage "RealityKit" rawValues
    // still decode and migrate to .map via normalizedViewDisplayMode(). Hidden
    // from every picker/menu; never offered by availableViewDisplayModes.
    case realitykit = "RealityKit"
    // DEPRECATED legacy alias (#2667). "Spatial (2D)" merged into Canvas (.map):
    // both now render Spatial2DCanvas off the shared canvasLayoutStore. The case
    // is retained ONLY so persisted/@SceneStorage "Spatial" rawValues still decode
    // and can be migrated to .map by normalizedViewDisplayMode(). It is hidden from
    // every picker/menu and never offered by availableViewDisplayModes.
    case spatial = "Spatial"
    case workspace = "Workspace"

    /// User-selectable cases (excludes the retired `.spatial` + `.realitykit`
    /// decode-only aliases, #2667).
    static var selectableCases: [ViewDisplayMode] {
        allCases.filter { $0 != .spatial && $0 != .realitykit }
    }

    var id: String { rawValue }

    /// User-facing label shown in menus/pickers. rawValue is preserved for
    /// persistence/XCUITest hooks — only label changes here.
    var label: String {
        switch self {
        case .table: "Columns"
        case .map: "Canvas"
        case .realitykit: "Space"
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
        case .map: "Canvas / node map"
        case .realitykit: "3D space view"
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
    .frame(height: MiniToolbar<EmptyView, EmptyView>.standardHeight)
    .onAppear {
        registry.createFolder = { print("Create folder") }
        registry.createSearch = { print("Create search") }
    }
}
