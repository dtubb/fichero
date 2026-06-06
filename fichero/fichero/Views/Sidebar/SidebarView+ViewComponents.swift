import AppKit
import SwiftUI

// MARK: - View Components

extension SidebarView {
    @ViewBuilder
    var sidebarContent: some View {
        if sidebarMode == .mindPalace {
            // Mind Palace mode shows its rooms list here; the canvas + node
            // inspector render in the main content area (MindPalaceContainer).
            RoomListView()
        } else {
            standardSidebarContent
        }
    }

    @ViewBuilder
    var standardSidebarContent: some View {
        VStack(spacing: 0) {
            // Breathing room between the window's title bar and the sidebar's
            // first row. Without this the 'Library' header sits flush against
            // the toolbar — feels cramped on macOS Tahoe / Sequoia. 12pt
            // matches Mail.app / Finder.app's sidebar-to-toolbar gap. (#883)
            Spacer()
                .frame(height: 12)

            if sidebarMode == .research {
                ResearchProjectListView()
            } else {
                unifiedContent
            }

            // Bottom toolbar (not shown for research — ResearchProjectListView has its own)
            if shouldShowBottomToolbar && sidebarMode != .research {
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

    /// Whether to show the bottom toolbar.
    var shouldShowBottomToolbar: Bool {
        true
    }

    /// Unified sidebar content with feature-gated sections per library.
    @ViewBuilder
    var unifiedContent: some View {
        List(selection: $selectedItemId) {
            ForEach(cachedLibraryHeaders) { libraryHeader in
                unifiedLibrarySection(libraryHeader)
            }
            // App-level destinations pinned once at the bottom, not repeated
            // under every library (#1456).
            pinnedGlobalNavigationRows()
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)
        // #883 — paint over the default sidebar NSVisualEffectView
        // (which renders darker than the content area) with the window
        // background colour so the sidebar tonally matches the content
        // pane. scrollContentBackground(.hidden) alone wasn't enough on
        // macOS — the NavigationSplitView's sidebar column has its own
        // material layer underneath. .background here paints over that.
        .background(Color(NSColor.windowBackgroundColor))
        .onDeleteCommand {
            deleteSelectedActivityRuns()
        }
    }
}
