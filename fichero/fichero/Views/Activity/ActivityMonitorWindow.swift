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
                ActivityBrowserView(
                    selectedRunId: selectionState.selectedRun?.id,
                    onSelectRun: { selectionState.select($0) },
                    showsOpenWindowButton: false,
                    opensDetailWindow: true
                )
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
        .frame(minWidth: 420, minHeight: 520)
    }
}

struct ActivityDetailWindow: View {
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
            if let library, let selectedRun = selectionState.selectedRun {
                ActivityDetailView(selectedRun: selectedRun)
                    .environment(library.activityStore)
                    .environment(library.apiClient)
                    .environment(library.workflowExecutionStore)
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

#if os(macOS)
struct ActivityWindowMenuButton: View {
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        Button("Activity") {
            openWindow(id: ActivityWindowSelectionState.monitorWindowID)
        }
    }
}
#endif
