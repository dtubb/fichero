import Observation
import SwiftUI

/// Tracks the state for a single window
/// Each window views one library and can have multiple tabs
@MainActor
@Observable
class WindowState {
    /// ID of the library this window is viewing
    var libraryId: UUID

    /// Currently selected tab
    var selectedTab: String = "library"

    /// The document selection a workflow run must honor (#4523 LAW: "a
    /// workflow's scope is the CURRENT SELECTION at gesture time; selection
    /// means the selected items, not their peers").
    ///
    /// Written by ContentView whenever the library-pane selection becomes
    /// non-empty, and — deliberately — NOT cleared by sidebar navigation:
    /// the #712 policy clears `browserSelection` the moment the user
    /// navigates (for example to a workflow node, in order to run it), which
    /// is exactly the moment the selection must be remembered. It IS cleared
    /// when the user selects a different library container (the browse
    /// context moved on, so a remembered selection would be stale scope).
    /// Every run surface reads its effective selection through this.
    var preservedDocumentSelection: [String] = []

    /// The LIVE library-pane selection, mirrored from `browserSelection` on
    /// every change — INCLUDING to empty. A sidebar row's context-menu run
    /// reads THIS, never the preserved snapshot: the snapshot can be
    /// arbitrarily old, and a stale multi-selection that happened to contain
    /// the clicked file expanded a one-file run onto every sibling
    /// (Daniel, 2026-08-15). Preservation keeps serving the workflow-editor
    /// surface it was built for (#4523); the live mirror serves surfaces
    /// where the user is pointing at a specific row RIGHT NOW.
    var liveDocumentSelection: [String] = []

    /// Why the last drop onto a library folder cell failed, or nil (#4474).
    /// Rendered by `LibraryView`'s drop alert. The sidebar has the same surface
    /// in `SidebarState.dropErrorMessage`; the library pane had none at all, so
    /// a failed cell drop was logged and otherwise looked exactly like a drop
    /// that had worked.
    var dropErrorMessage: String?

    /// Monotonic request token for "open the workflow picker over the current
    /// selection" (the island's ⚡ chip). A counter, not a Bool: LibraryView
    /// reacts to the CHANGE, so pressing the chip again after dismissing the
    /// picker fires again. Direct @Observable seam per §6b — never a
    /// NotificationCenter post.
    var workflowPickerRequestToken = 0

    /// A contextual suggestion button was pressed (2026-08-25): run THIS
    /// default workflow (by canonical name — ids are per-library) over the
    /// current selection. Token-stamped so the same button fires twice.
    struct SuggestedWorkflowRequest: Equatable {
        let workflowName: String
        let token: Int
    }
    var suggestedWorkflowRequest: SuggestedWorkflowRequest?

    /// Ephemeral rubber-band selections drawn over this window's Preview
    /// image (Daniel, 2026-08-29). Lives HERE so it is per-window by
    /// construction — the workflow bar reads it as a run scope, and two
    /// windows' marquees must never mix. See `PreviewMarqueeSelection`.
    let previewMarquees = PreviewMarqueeSelection()

    /// The annotation bar's ARMED tool (Daniel, 2026-08-30: "when we change
    /// tools for markup… leave it selected"). Sticky: the tool stays armed
    /// across uses until toggled off or another tool is armed; canvases read
    /// it for behaviour and cursor. Per-window, like the marquee seam.
    /// Select is ON from the first click (Daniel, 2026-09-02: "Selection
    /// should default on") — a window opens able to select regions without
    /// first opening the markup bar.
    var activeMarkupTool: PreviewMarkupTool? = .select

    /// Coding v1 (Daniel, 2026-08-30, ruling 4): comma-separated tags entered
    /// via the highlight menu's "Tag Next Highlight…" ride the NEXT saved
    /// highlight / underline / strikethrough / check, then clear — one-shot,
    /// per-window like the armed tool. Canvases consume via
    /// `takePendingMarkupTags()` at the save site.
    var pendingMarkupTags: [String] = []

    /// One-shot read of `pendingMarkupTags`: returns them and clears, so a
    /// multi-strip save (word-snapped highlight) tags every strip of ONE
    /// gesture but never the next gesture.
    func takePendingMarkupTags() -> [String] {
        let tags = pendingMarkupTags
        pendingMarkupTags = []
        return tags
    }

    init(libraryId: UUID) {
        self.libraryId = libraryId
    }

    /// Get the library reference from LibraryManager
    var library: LibraryManager.LibraryReference? {
        LibraryManager.shared.getLibrary(id: libraryId)
    }

    /// Get the APIClient for this window's library
    var apiClient: APIClient? {
        library?.apiClient
    }

    /// Get the document for this window's library
    var document: FicheroDocument? {
        library?.document
    }
}
