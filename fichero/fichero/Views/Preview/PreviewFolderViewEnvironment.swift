import SwiftUI

/// Injected per Preview leaf so the head's "Show folder as" menu writes THIS pane's choice into the
/// stored pane list (`PaneList.changingLeafPreviewFolderView`), as `PaneKindSwitcher` does for the
/// kind (`library.preview.folder-view-persists-per-pane`). nil = a Preview outside a pane slot.
/// Equatable by slot id only, for the same reason `PaneKindSwitcher` is (a closure is never `==`).
struct PanePreviewFolderViewSwitcher: Equatable {
    let slotId: String
    let switchFolderView: @MainActor (PreviewFolderView) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool { lhs.slotId == rhs.slotId }
}

extension EnvironmentValues {
    /// THIS pane's stored folder view (`PaneConfig.previewFolderView`), published by
    /// `ContentView.paneNodeView` like `\.paneLibraryLayout`. nil = never chosen (the default, Table).
    @Entry var panePreviewFolderView: String?
    @Entry var panePreviewFolderViewSwitcher: PanePreviewFolderViewSwitcher?
}
