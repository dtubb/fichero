import SwiftUI

// MARK: - Display Helpers

extension LibraryView {
    /// Mail-style selection (#4191): the focused/unfocused split lives in the
    /// LABEL tint — accent when this pane drives keyboard input, secondary
    /// otherwise. The fill itself is the constant subtle grey
    /// (`LibrarySelectionStyle.fill`) in both states, replacing the #3875
    /// solid-accent focused fill.
    var selectionTint: Color {
        isPaneFocused ? .accentColor : .secondary
    }

    var browserLeadingInset: CGFloat { 12 }
}
