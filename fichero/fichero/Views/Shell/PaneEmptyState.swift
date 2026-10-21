import SwiftUI

/// What an empty pane says to VoiceOver: which pane it is and what would fill it (#5273). Drawn BLANK. The Library pane
/// has no entry: it always shows its location, even an empty one.
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
        case .reader: return "Select a page in \(ItemsPane.name) to read it."
        case .preview: return "Select a page to see it here."
        case .inspector: return "Select an item to see its details."
        }
    }

    /// Blank (`panes.empty-state.blank`, ruled 2026-10-11): the title and hint are VoiceOver's, not drawn.
    var view: some View {
        Color.clear
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .accessibilityElement()
            .accessibilityLabel(title)
            .accessibilityHint(hint)
            .accessibilityIdentifier("paneEmptyState.\(rawValue)")
    }
}
