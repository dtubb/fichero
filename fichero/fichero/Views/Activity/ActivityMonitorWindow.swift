import SwiftUI

/// Root of the poppable "Activity" window (#2546 / B2) — the window *is* the
/// hierarchical monitor table.
///
/// It resolves the active library from `LibraryManager` and injects exactly the
/// environment `ActivityMonitorView` needs: the shared `WorkflowExecutionStore`
/// (live data) and the library's `APIClient` (log fetch + pause/stop). The
/// `WorkflowExecutionObserver` arrives from the `WindowGroup` (the app-level
/// fallback observer). The store is shared per-library, so this detached window
/// shows the same live runs as the in-sidebar Activity surface.
struct ActivityMonitorWindow: View {
    @Environment(LibraryManager.self) private var libraryManager
    @State private var selectionState = ActivityWindowSelectionState.shared

    private var library: LibraryManager.LibraryReference? {
        if let id = libraryManager.currentLibraryId,
           let library = libraryManager.getLibrary(id: id) {
            return library
        }
        return libraryManager.globalLibrary
    }

    var body: some View {
        Group {
            if let library {
                HStack(spacing: 0) {
                    ActivityBrowserView(
                        selectedRunId: selectionState.selectedRun?.id,
                        onSelectRun: { selectionState.select($0) },
                        showsOpenWindowButton: false
                    )
                    .frame(minWidth: 240, idealWidth: 280, maxWidth: 320)

                    Divider()

                    if let selectedRun = selectionState.selectedRun {
                        ActivityDetailView(selectedRun: selectedRun)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else {
                        ContentUnavailableView(
                            "Select a Run",
                            systemImage: "clock",
                            description: Text("Choose a workflow run from the list to inspect it.")
                        )
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    }
                }
                .environment(library.activityStore)
                .environment(library.apiClient)
                .environment(library.workflowExecutionStore)
            } else {
                ContentUnavailableView(
                    "No Library Open",
                    systemImage: "tray",
                    description: Text("Open a library to monitor its workflow activity.")
                )
            }
        }
        .navigationTitle("Activity")
        .frame(minWidth: 900, minHeight: 520)
    }
}
