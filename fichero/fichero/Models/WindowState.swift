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
