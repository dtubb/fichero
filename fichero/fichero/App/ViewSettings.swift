import SwiftUI

/// Observable settings for view configuration (app-wide preferences)
/// Note: sidebarMode is NOT here - it's per-window state stored in @SceneStorage
@MainActor
class ViewSettings: ObservableObject {
    @Published var libraryLayout: LibraryLayout = .icons
    @Published var previewMode: PreviewMode = .widescreen
    // NOTE: inspector visibility is intentionally NOT here. It is per-window
    // state (`ContentView.showInspectorSidebar`, @SceneStorage) exposed to the
    // View menu via `FocusedValues.showInspector` below, so toggling the
    // inspector in one window no longer flips it in every other window (#1451).
}

// MARK: - View Mode Enums

/// Sidebar mode selection - Xcode-style mode switching
/// Order: Content (1-4), Research (5), Automation (6), Monitoring (7), KG (9)
enum SidebarMode: String, CaseIterable {
    case library      // 1: Documents, folders
    case search       // 2: Saved searches + search bar
    case chat         // 3: Conversations
    case workflows    // 4: Workflow definitions
    case automation   // 5: Schedules + triggers
    case activity       // 6: All workflow runs (running + completed + failed) with logs/errors
    case mindPalace     // 7: Spatial 3D-2D space — rooms of archival material
    case research       // 8: Research projects + workspace
    case knowledgeGraph // 9: Entity / ontology browser (#498)

    /// SF Symbol icon name for this mode
    var icon: String {
        switch self {
        case .library: "folder"
        case .search: "magnifyingglass"
        case .chat: "bubble.left.and.bubble.right"
        case .workflows: "bolt"
        case .research: "flask"
        case .automation: "gearshape.2"
        case .activity: "clock"
        case .mindPalace: "cube.transparent"
        case .knowledgeGraph: "point.3.connected.trianglepath.dotted"
        }
    }

    /// Display label for menus
    var label: String {
        switch self {
        case .library: "Library"
        case .search: "Search"
        case .chat: "Chat"
        case .workflows: "Workflows"
        case .research: "Research"
        case .automation: "Automation"
        case .activity: "Activity"
        case .mindPalace: "Mind Palace"
        case .knowledgeGraph: "Knowledge Graph"
        }
    }

    /// Keyboard shortcut number (1-9)
    var shortcutNumber: String {
        switch self {
        case .library: "1"
        case .search: "2"
        case .chat: "3"
        case .workflows: "4"
        case .automation: "5"
        case .activity: "6"
        case .mindPalace: "7"
        case .research: "8"
        case .knowledgeGraph: "9"
        }
    }

    /// Tooltip copy: what the mode shows and how to reach it. (#1371)
    var helpText: String {
        let body: String
        switch self {
        case .library:
            body = "Library — browse your documents and folders"
        case .search:
            body = "Search — saved searches and full-text search across the library"
        case .chat:
            body = "Chat — ask questions about your documents in a conversation"
        case .workflows:
            body = "Workflows — build and run AI processing pipelines"
        case .research:
            body = "Research — research projects and their workspace"
        case .automation:
            body = "Automation — schedules and triggers that run workflows automatically"
        case .activity:
            body = "Activity — monitor running and recent background jobs"
        case .mindPalace:
            body = "Mind Palace — a spatial 3D view of your documents"
        case .knowledgeGraph:
            body = "Knowledge Graph — explore entities and how they connect"
        }
        return "\(body) (⌘\(shortcutNumber))"
    }
}

/// Library layout modes
enum LibraryLayout: String, CaseIterable, Codable {
    case icons = "Icons"
    case list = "List"
    case table = "Table"
    case map = "Map"

    var icon: String {
        switch self {
        case .icons: "square.grid.2x2"
        case .list: "list.bullet"
        case .table: "tablecells"
        case .map: "rectangle.3.group"
        }
    }
}

/// Preview panel mode (matches LayoutMode)
enum PreviewMode: String, CaseIterable {
    case none
    case standard   // Content and preview stacked vertically
    case widescreen // Content and preview side-by-side
}

// MARK: - Focused Values

/// Focused value for sidebar mode - allows menu commands to change per-window sidebar mode
extension FocusedValues {
    @Entry var sidebarMode: Binding<SidebarMode>?

    /// Per-window inspector visibility, published by the focused ContentView so
    /// the View-menu "Show/Hide Inspector" command toggles only the focused
    /// window — not every open window (#1451).
    @Entry var showInspector: Binding<Bool>?
}
