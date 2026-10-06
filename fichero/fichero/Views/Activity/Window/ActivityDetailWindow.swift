import SwiftUI

/// Root of the standalone "Activity Details" window, opened by a row's ⓘ and by
/// double-click (#5560). It mounts the one details view (#5561) for the
/// selected row's job, read through the row's own project: a row always
/// carries its project, so the current or the global library is only the
/// fallback for a selection made without one.
struct ActivityDetailWindow: View {
    @Environment(LibraryManager.self) private var libraryManager
    @State private var selectionState = ActivityWindowSelectionState.shared

    private var library: LibraryManager.LibraryReference? {
        if let id = selectionState.selection?.libraryId ?? selectionState.libraryId,
           let library = libraryManager.getLibrary(id: id) {
            return library
        }
        if let id = libraryManager.currentLibraryId,
           let library = libraryManager.getLibrary(id: id) {
            return library
        }
        return libraryManager.globalLibrary
    }

    var body: some View {
        Group {
            if let library, let selection = selectionState.selection {
                ActivityDetailsView(selection: selection)
                    // The ONE service list, never a hand-picked subset: this window's own copy once
                    // omitted ArtifactService and TRAPPED the moment a run with artifacts was opened
                    // (#4284) -- a missing @Environment object is a fatal error, not a nil.
                    .libraryServiceEnvironment(library)
            } else {
                ContentUnavailableView(
                    "No Activity Selected",
                    systemImage: "info.circle",
                    description: Text("Double-click a row in the Activity window to see its details.")
                )
            }
        }
        .navigationTitle("Activity Details")
        .frame(minWidth: 520, minHeight: 420)
    }
}
