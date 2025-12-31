import SwiftUI

/// Observable settings for view configuration
@MainActor
class ViewSettings: ObservableObject {
    @Published var sidebarMode: SidebarMode = .navigate
    @Published var libraryLayout: LibraryLayout = .icons
    @Published var previewMode: PreviewMode = .standard
    @Published var showInspector: Bool = true
    @Published var showQuickLook: Bool = false
}

// MARK: - View Mode Enums

/// Sidebar mode selection
enum SidebarMode: String, CaseIterable {
    case navigate
    case search
    case chat
    case workflows
    case activity
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

/// Preview panel mode
enum PreviewMode: String, CaseIterable {
    case none
    case standard   // Side by side (horizontal)
    case widescreen // Browser above preview (vertical)
}
