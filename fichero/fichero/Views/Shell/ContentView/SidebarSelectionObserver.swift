import SwiftUI

/// Watches the sidebar's selection for the window, so the window itself does not (#4228).
///
/// `ContentView` carried these `.onChange(of: sidebarSelectionState…)` modifiers itself. An
/// `onChange` reads its value while the body is built, so a click re-evaluated the whole window
/// (the content column, the sidebar and every pane head) just to draw the new highlight. Here only
/// this empty view re-runs; the window updates only when a handler changes its state, which a
/// click on a folder does in its routing step, after the highlight is drawn
/// (`sidebar.selection.highlight-first`).
///
/// Its identity is stable (no `.id`), and the order of the observers is the order they had on
/// `ContentView`: the multi-selection scope before the single-id handler, so a shrink-to-one still
/// lets the navigate path run after the scope check declines it.
struct SidebarSelectionObserver: View {
    let selection: SidebarSelectionState
    let onDestinationsChange: (Set<SidebarDestination>) -> Void
    let onReopen: () -> Void
    let onSelectedItemIdChange: (String?) -> Void
    let onReveal: () -> Void

    var body: some View {
        Color.clear
            .frame(width: 0, height: 0)
            .accessibilityHidden(true)
            .onChange(of: selection.selectedDestinations) { _, new in onDestinationsChange(new) }
            .onChange(of: selection.reopenGeneration) { _, _ in onReopen() }
            .onChange(of: selection.selectedItemId) { _, new in onSelectedItemIdChange(new) }
            .onChange(of: selection.revealGeneration) { _, _ in onReveal() }
    }
}
