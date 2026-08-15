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

    /// EVERY open library, global included (Daniel #19: "show ALL
    /// libraries") — the window used to show only the selection-state
    /// library, so runs in any other open library were invisible here.
    private var libraries: [LibraryManager.LibraryReference] {
        var references = libraryManager.openLibraries
        if let global = libraryManager.globalLibrary,
           !references.contains(where: { $0.id == global.id }) {
            references.append(global)
        }
        return references
    }

    var body: some View {
        Group {
            if libraries.isEmpty {
                ContentUnavailableView(
                    "No Library Open",
                    systemImage: "tray",
                    description: Text("Open a library to monitor its workflow activity.")
                )
            } else {
                // One section per library, each its own scrolling run list —
                // the Xcode-Organizer shape. Each browser is bound to ITS
                // library's stores; selection flows through the shared
                // selection state, which already carries the libraryId the
                // detail window resolves against.
                VStack(spacing: 0) {
                    ForEach(libraries) { library in
                        librarySection(library)
                    }
                }
            }
        }
        .navigationTitle("Activity")
        .frame(minWidth: 420, minHeight: 520)
    }

    @ViewBuilder
    private func librarySection(_ library: LibraryManager.LibraryReference) -> some View {
        VStack(spacing: 0) {
            Label(library.displayName, systemImage: "books.vertical")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
            Divider()
            ActivityBrowserView(
                selectedRunId: selectionState.selectedRun?.id,
                onSelectRun: { selectionState.select($0) },
                showsOpenWindowButton: false,
                opensDetailWindow: true
            )
            .environment(library.activityStore)
            .environment(library.apiClient)
            .environment(library.workflowExecutionStore)
            .frame(minHeight: 160, maxHeight: .infinity)
        }
    }
}

// ActivityWindowMenuButton was deleted with #4524: the `Window("Activity")`
// scene's automatic Windows-menu item (see FicheroApp scene declarations) is
// the one entry point, so a hand-rolled CommandGroup button was a duplicate.
