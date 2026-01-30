import SwiftUI

/// Observable settings for view configuration (app-wide preferences)
/// Note: sidebarMode is NOT here - it's per-window state stored in @SceneStorage
@MainActor
class ViewSettings: ObservableObject {
    @Published var libraryLayout: LibraryLayout = .icons
    @Published var previewMode: PreviewMode = .standard
    @Published var showInspector: Bool = true
    @Published var showQuickLook: Bool = false
}

// MARK: - View Mode Enums

/// Sidebar mode selection - Xcode-style mode switching
/// Order: Content (1-4), Automation (5-6), Monitoring (7)
enum SidebarMode: String, CaseIterable {
    case library      // 1: Documents, folders
    case search       // 2: Saved searches + search bar
    case chat         // 3: Conversations
    case workflows    // 4: Workflow definitions
    case batches      // 5: Multi-item batch jobs
    case automation   // 6: Schedules + triggers
    case activity     // 7: All workflow runs (running + completed + failed) with logs/errors

    /// SF Symbol icon name for this mode
    var icon: String {
        switch self {
        case .library: return "folder"
        case .search: return "magnifyingglass"
        case .chat: return "bubble.left.and.bubble.right"
        case .workflows: return "bolt"
        case .batches: return "shippingbox"
        case .automation: return "gearshape.2"
        case .activity: return "clock"
        }
    }

    /// Display label for menus
    var label: String {
        switch self {
        case .library: return "Library"
        case .search: return "Search"
        case .chat: return "Chat"
        case .workflows: return "Workflows"
        case .batches: return "Batches"
        case .automation: return "Automation"
        case .activity: return "Activity"
        }
    }

    /// Keyboard shortcut number (1-7)
    var shortcutNumber: String {
        switch self {
        case .library: return "1"
        case .search: return "2"
        case .chat: return "3"
        case .workflows: return "4"
        case .batches: return "5"
        case .automation: return "6"
        case .activity: return "7"
        }
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
        case .icons: return "square.grid.2x2"
        case .list: return "list.bullet"
        case .table: return "tablecells"
        case .map: return "rectangle.3.group"
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
}
