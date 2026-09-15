import SwiftUI

/// Closes THE pane it is attached to, by removing that leaf from the window's applied `PaneList`
/// (spec panes.close.this-pane-only). Published into the environment per-leaf by
/// `ContentView.paneNodeView` on the applied-workspace path; `PaneHead`'s X prefers it over the
/// split-collapse and the legacy `onClose`, so closing one pane never drops its siblings or the row
/// — `PaneList.removingLeaf(id)` collapses a singleton split to its survivor and removes a top-level
/// pane in the same operation. nil everywhere else, where the existing close behaviour stands.
/// `@unchecked Sendable` to satisfy the EnvironmentKey `defaultValue` (Swift 6 strict concurrency),
/// the same way `SplitAxisActions` does: the closure is only ever built and invoked on the MainActor
/// (SwiftUI environment + the pane head's button action).
struct PaneCloseAction: @unchecked Sendable {
    let run: () -> Void
}

private struct PaneCloseActionKey: EnvironmentKey {
    static let defaultValue: PaneCloseAction? = nil
}

extension EnvironmentValues {
    var paneCloseAction: PaneCloseAction? {
        get { self[PaneCloseActionKey.self] }
        set { self[PaneCloseActionKey.self] = newValue }
    }
}
