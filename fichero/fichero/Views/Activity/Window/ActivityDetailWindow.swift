import SwiftUI

/// Root of the standalone "Activity Detail" window. The monitor
/// (`ActivityMonitorWindow`) opens this window on double-click; the detail view
/// lives here alone so the monitor window never inlines it. Resolves the active
/// library and injects the same per-library stores as the monitor so the
/// detached detail shows the same live run.
struct ActivityDetailWindow: View {
    @Environment(LibraryManager.self) private var libraryManager
    @State private var selectionState = ActivityWindowSelectionState.shared

    private var library: LibraryManager.LibraryReference? {
        if let id = selectionState.selectedRun?.libraryId ?? selectionState.libraryId,
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
            if let library, let selectedRun = selectionState.selectedRun {
                ActivityDetailView(selectedRun: selectedRun)
                    // The ONE service list, never a hand-picked subset: this window's own copy once
                    // omitted ArtifactService and TRAPPED the moment a run with artifacts was opened
                    // (#4284) -- a missing @Environment object is a fatal error, not a nil.
                    .libraryServiceEnvironment(library)
            } else {
                ContentUnavailableView(
                    "No Activity Selected",
                    systemImage: "info.circle",
                    description: Text("Double-click a run in the Activity window to inspect it.")
                )
            }
        }
        .navigationTitle("Activity Details")
        .frame(minWidth: 720, minHeight: 520)
    }
}
