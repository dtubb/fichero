import SwiftUI

/// What an empty pane says: which pane it is and what would fill it (#5273). A row of identical
/// "No selection" labels did neither. Same shape as the Segments pane's `ContentUnavailableView`
/// (icon, title, one line of what to do). The Library pane has no entry: it always shows its
/// location, even an empty one.
enum PaneEmptyState: String, CaseIterable {
    case reader
    case preview
    case inspector

    var title: String {
        switch self {
        case .reader, .preview: return "No Page"
        case .inspector: return "Nothing Selected"
        }
    }

    var systemImage: String {
        switch self {
        case .reader: return "doc.text"
        case .preview: return "photo"
        case .inspector: return "info.circle"
        }
    }

    var hint: String {
        switch self {
        case .reader: return "Select a page in the Library to read it."
        case .preview: return "Select a page to see it here."
        case .inspector: return "Select an item to see its details."
        }
    }

    var view: some View {
        ContentUnavailableView(title, systemImage: systemImage, description: Text(hint))
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .accessibilityIdentifier("paneEmptyState.\(rawValue)")
    }
}
