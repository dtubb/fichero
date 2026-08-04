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

    /// Why the last drop onto a library folder cell failed, or nil (#4474).
    /// Rendered by `LibraryView`'s drop alert. The sidebar has the same surface
    /// in `SidebarState.dropErrorMessage`; the library pane had none at all, so
    /// a failed cell drop was logged and otherwise looked exactly like a drop
    /// that had worked.
    var dropErrorMessage: String?

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
