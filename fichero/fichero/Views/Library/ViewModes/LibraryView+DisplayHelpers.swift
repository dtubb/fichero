import SwiftUI

// MARK: - Display Helpers

extension LibraryView {
    var selectionTint: Color {
        isPaneFocused ? .accentColor : .secondary
    }

    /// Row/tile background highlight (#3875). When the pane is FOCUSED the
    /// selected item shows a real Finder-blue fill, not a 12% wash; when the
    /// pane isn't focused it stays a faint gray — the same focused/unfocused
    /// split as `selectionTint`, just at fill strength.
    var selectionFill: Color {
        isPaneFocused ? Color.accentColor.opacity(0.85) : Color.secondary.opacity(0.12)
    }

    var browserLeadingInset: CGFloat { 12 }
}
