import SwiftUI

// MARK: - View Components

extension SidebarView {
    @ViewBuilder
    var sidebarContent: some View {
        standardSidebarContent
    }

    @ViewBuilder
    var standardSidebarContent: some View {
        VStack(spacing: 0) {
            // The persistent shell sidebar (the library/folder tree) stays
            // visible in EVERY mode — Research included. Research no longer
            // swaps the sidebar out for its project list; that list now renders
            // in the content column (ContentView+Navigation.contentView), so
            // switching to Research keeps the shell sidebar like Knowledge Graph,
            // Activity, etc. (sidebar-persistence fix).
            unifiedContent

            // Bottom toolbar — owns the sidebar filter field + sidebar-scoped
            // actions as one unified bottom toolbar (#4061). No standalone
            // filter chrome above the bar.
            if shouldShowBottomToolbar {
                SidebarBottomToolbar(
                    createSearch: createNewSearch,
                    createChat: createNewChat,
                    createWorkflow: createNewWorkflow,
                    createFolder: handleCreateNewFolder,
                    importFiles: importFiles,
                    createComparison: createNewComparison,
                    createSchedule: createNewSchedule,
                    createTrigger: createNewTrigger,
                    deleteItem: handleDeleteSelection,
                    hasSelection: selectedItem != nil,
                    sidebarFilterText: $sidebarFilterText
                )
            }
        }
    }

    /// Whether to show the bottom toolbar.
    var shouldShowBottomToolbar: Bool {
        true
    }

    /// Unified sidebar content with feature-gated sections per library.
    @ViewBuilder
    var unifiedContent: some View {
        List(selection: sidebarSelectionBinding) {
            ForEach(filteredLibraryHeaders) { libraryHeader in
                unifiedLibrarySection(libraryHeader)
            }
            // App-level destinations pinned once at the bottom, not repeated
            // under every library (#1456).
            pinnedGlobalNavigationRows()
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)
        .background(.bar)
        #if os(macOS)
        // Finder-style double-click: open the primary selected row in a new
        // tab or window (#2496), mirroring the library table's container-level
        // double-click contract (#3364). Attached to the List, NOT per row —
        // a row-level TapGesture(count: 2) holds every single click and
        // breaks native List selection (#612). Keyboard/VoiceOver users reach
        // the same action via the row context menu's Open in New Tab/Window.
        .onTapGesture(count: 2) {
            handleSidebarDoubleClick()
        }
        // Delete key removes the whole (deletable) multi-selection, confirming once.
        .onDeleteCommand {
            handleDeleteSelection()
        }
        // Escape collapses a multi-row selection back to the single routed
        // anchor ("shift to stop it"). Plain-click collapse is already native.
        .onExitCommand {
            selectionState.selectedDestinations =
                sidebarCollapsedSelection(primary: selectionState.selectedDestination)
        }
        #endif
    }

    /// Bridges the sidebar tree's native multi-selection to the state.
    ///
    /// macOS `List(selection: Binding<Set>)` gives shift-click contiguous
    /// range, cmd-click toggle, and shift+arrow extend for free. The setter is
    /// the one seam that derives the routed primary (`selectedDestination`,
    /// which drives the detail pane and `.onChange` routing) from the highlight
    /// set. Write ORDER matters: set `selectedDestinations` first so the primary
    /// is derived from the current set, never a stale one.
    private var sidebarSelectionBinding: Binding<Set<SidebarDestination>> {
        Binding(
            get: { selectionState.selectedDestinations },
            set: { newValue in
                selectionState.selectedDestinations = newValue
                let primary = sidebarPrimaryDestination(
                    for: newValue,
                    previous: selectionState.selectedDestination
                )
                // Only reroute when the primary actually changes — a >1 batch
                // selection returns the same primary, so this is a no-op and the
                // detail pane stays put while the selection is built.
                if selectionState.selectedDestination != primary {
                    selectionState.selectedDestination = primary
                }
            }
        )
    }
}
