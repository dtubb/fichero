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

            sidebarFilterBar

            // Bottom toolbar.
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
                    deleteItem: handleDeleteSelectedItem,
                    hasSelection: selectedItem != nil
                )
            }
        }
    }

    /// Whether to show the bottom toolbar.
    var shouldShowBottomToolbar: Bool {
        true
    }

    private var sidebarFilterBar: some View {
        PaneFilterBar {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.secondary)
            TextField("Filter", text: $sidebarFilterText)
                .textFieldStyle(.plain)
                .accessibilityIdentifier("sidebarFilterField")
            if !sidebarFilterText.isEmpty {
                Button {
                    sidebarFilterText = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .help("Clear filter")
                .accessibilityLabel("Clear filter")
            }
        }
    }

    /// Unified sidebar content with feature-gated sections per library.
    @ViewBuilder
    var unifiedContent: some View {
        List(selection: $selectionState.selectedItemId) {
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
        .onDeleteCommand {
            deleteSelectedActivityRuns()
        }
        #endif
    }
}
