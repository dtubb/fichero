import Foundation

/// Layout modes for the main content area
/// Inspired by DevonThink's view menu
enum LayoutMode: String, CaseIterable, Identifiable {
    case none = "None"
    case standard = "Standard"
    case widescreen = "Widescreen"

    var id: String { rawValue }

    /// SF Symbol icon for toolbar
    var icon: String {
        switch self {
        case .none:
            // No preview - just content (no split)
            return "square"
        case .standard:
            // Vertical split - content above preview (1 column, 2 rows)
            return "rectangle.split.1x2"
        case .widescreen:
            // Horizontal split - content beside preview (2 columns, 1 row)
            return "rectangle.split.2x1"
        }
    }

    /// Description for menu items
    var description: String {
        switch self {
        case .none:
            return "Content only, no preview"
        case .standard:
            return "Content and preview side-by-side"
        case .widescreen:
            return "Content and preview stacked vertically"
        }
    }

    /// Keyboard shortcut (optional)
    var keyboardShortcut: String? {
        switch self {
        case .none: return "0"
        case .standard: return "1"
        case .widescreen: return "2"
        }
    }
}
