import Foundation

/// Focus mode's one window rule (`panes.focus-mode`, #6575; owner 2026-11-13: real macOS full screen): entering takes the
/// window into its own full screen only if it is not already there, and leaving undoes only what entering did, so a
/// window that was already full screen stays full screen.
enum FocusMode {
    /// Whether entering focus should toggle the window into full screen.
    static func entersFullScreen(windowIsFullScreen: Bool) -> Bool { !windowIsFullScreen }

    /// Whether leaving focus should toggle the window back out: only when focus put it there and it is still there.
    static func leavesFullScreen(focusEnteredIt: Bool, windowIsFullScreen: Bool) -> Bool {
        focusEnteredIt && windowIsFullScreen
    }

    /// What ⌃⌘R (View › Focus on Pane) does (`panes.focus.any-pane-fills-the-screen`, owner ruling 7: one chord, the wider
    /// meaning): leave a pane's Focus; on a Preview showing a page (or with no pane focused) open the page reader, the
    /// Preview's Focus; on any other pane, or a Source showing a folder, focus that pane.
    enum Step: Equatable {
        case leave
        case readPage
        case focus(UUID)
        case nothing
    }

    static func step(focusedNow: UUID?, focusedKind: PaneKind?, focusedLeaf: UUID?, hasPage: Bool) -> Step {
        if focusedNow != nil { return .leave }
        if hasPage, focusedKind == .preview || focusedLeaf == nil { return .readPage }
        return focusedLeaf.map(Step.focus) ?? .nothing
    }
}
