import SwiftUI

// MARK: - View Components

extension SidebarView {
    @ViewBuilder
    var sidebarContent: some View {
        VStack(spacing: 0) {
            // Mode bar at top (Xcode-style)
            SidebarModeBar(selectedMode: $sidebarMode)

            Divider()

            // Content based on selected mode
            modeContent

            // Bottom toolbar (only show for content creation modes)
            if shouldShowBottomToolbar {
                Divider()
                SidebarBottomToolbar(
                    createSearch: createNewSearch,
                    createChat: createNewChat,
                    createWorkflow: createNewWorkflow,
                    createFolder: handleCreateNewFolder,
                    importFiles: importFiles,
                    createComparison: createNewComparison,
                    createSchedule: createNewSchedule,
                    createTrigger: createNewTrigger
                )
            }
        }
    }

    /// Whether to show the bottom toolbar (only for content modes)
    var shouldShowBottomToolbar: Bool {
        switch sidebarMode {
        case .library, .search, .chat, .workflows, .automation:
            return true
        case .batches, .activity:
            return false
        }
    }

    /// Content view based on selected sidebar mode
    @ViewBuilder
    var modeContent: some View {
        switch sidebarMode {
        case .library:
            LibrarySidebarContent(
                selectedItemId: $selectedItemId,
                libraryManager: libraryManager,
                sidebarState: sidebarState,
                renameState: renameState,
                deleteState: deleteState,
                cachedLibraryHeaders: cachedLibraryHeaders
            )

        case .search:
            SearchSidebarContent(
                selectedItemId: $selectedItemId,
                libraryManager: libraryManager,
                sidebarState: sidebarState,
                renameState: renameState,
                deleteState: deleteState,
                cachedLibraryHeaders: cachedLibraryHeaders
            )

        case .chat:
            ChatSidebarContent(
                selectedItemId: $selectedItemId,
                viewMode: $viewMode,
                sidebarMode: $sidebarMode,
                libraryManager: libraryManager,
                sidebarState: sidebarState,
                renameState: renameState,
                deleteState: deleteState,
                cachedLibraryHeaders: cachedLibraryHeaders
            )

        case .workflows:
            WorkflowsSidebarContent(
                selectedItemId: $selectedItemId,
                viewMode: $viewMode,
                libraryManager: libraryManager,
                sidebarState: sidebarState,
                renameState: renameState,
                deleteState: deleteState,
                cachedLibraryHeaders: cachedLibraryHeaders,
                chains: chains,
                chainService: chainService
            )

        case .batches:
            BatchesSidebarContent(
                libraryManager: libraryManager,
                selectedItemId: $selectedItemId,
                viewMode: $viewMode,
                sidebarState: sidebarState,
                renameState: renameState,
                deleteState: deleteState,
                batches: batches,
                isLoading: batchesIsLoading,
                onRefresh: { Task { await loadBatchData() } }
            )

        case .automation:
            AutomationSidebarContent(
                libraryManager: libraryManager,
                selectedItemId: $selectedItemId,
                viewMode: $viewMode,
                sidebarState: sidebarState,
                renameState: renameState,
                deleteState: deleteState,
                schedules: schedules,
                triggers: triggers,
                isLoading: automationIsLoading,
                onRefresh: { Task { await loadAutomationData() } }
            )

        case .activity:
            ActivitySidebarContent(
                libraryManager: libraryManager,
                sidebarState: sidebarState,
                selectedItemId: $selectedItemId,
                viewMode: $viewMode,
                historicalRunsByLibrary: historicalRunsByLibrary,
                isLoading: activityIsLoading,
                onRefresh: { Task { await loadActivityData() } }
            )
        }
    }
}
