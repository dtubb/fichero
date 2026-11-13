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
}
