import SwiftUI

// MARK: - ContentView UI & Display Actions

extension ContentView {

    // MARK: - UI Actions

    func toggleSidebar() {
        if horizontalSizeClass == .compact || shouldUseRuntimeSidebarCollapse {
            return
        }
        withAnimation(FrameAnimation.snappy) {
            showSidebar.toggle()
            updateColumnVisibility()
        }
    }

    func handleWindowWidthChange(_ newWidth: Double) {
        guard newWidth > 0 else { return }
        // Views audit B3: a divider drag changes pane geometry every frame;
        // recomputing column visibility mid-drag rewrote columnVisibility and
        // invalidated the whole NavigationSplitView WHILE dragging. The
        // window itself cannot resize during a divider drag, so deferring is
        // free; the next real window resize re-runs this.
        guard !dividerDragInFlight else { return }
        if abs(measuredWindowWidth - newWidth) < 0.5 {
            return
        }
        measuredWindowWidth = newWidth
        updateColumnVisibility()
    }

    func updateColumnVisibility() {
        if horizontalSizeClass == .compact {
            return
        }
        // No animation — instant sidebar show/hide (#2309).
        if shouldUseRuntimeSidebarCollapse {
            columnVisibility = .detailOnly
        } else {
            columnVisibility = showSidebar ? .all : .detailOnly
        }
    }

    // MARK: - View Display & Layout

    func updateViewDisplayMode(_ requestedMode: ViewDisplayMode) {
        let effectiveMode = normalizedViewDisplayMode(requestedMode)
        if effectiveMode != viewDisplayMode {
            viewDisplayMode = effectiveMode
        }

        viewSettings.libraryLayout = effectiveMode.libraryLayout
        // NO per-folder save at all (Daniel's final #4575 ruling, 2026-08-09:
        // the mode never follows the folder). A pick is window-wide, promoted
        // to the global default so a fresh window / new launch starts in this
        // mode (#943). The per-folder map is dead — restore removed from
        // handleSidebarSelectionChange, menu items removed, map wiped by the
        // one-time migration.
        defaultLibraryViewDisplayMode = effectiveMode
    }

    func updateLayoutMode(_ requestedMode: LayoutMode) {
        guard availableLayoutModes.contains(requestedMode) else { return }

        let previewMode: PreviewMode = switch requestedMode {
        case .none: .none
        case .standard: .standard
        case .widescreen: .widescreen
        }

        viewSettings.previewMode = normalizedPreviewMode(previewMode)
        currentLayoutMode = requestedMode

        // Legacy-recovery net: a window persisted with all panes hidden (before
        // the #1696 invariant existed) gets a pane back on entering widescreen.
        // The invariant makes all-hidden unreachable for new state.
        if requestedMode == .widescreen, !paneVisibility.isAnyVisible {
            setPaneVisible(.canvas, true)
        }
    }

    func setCanvasPaneVisible(_ isVisible: Bool) {
        if isVisible {
            currentLayoutMode = .widescreen
            viewSettings.previewMode = .widescreen
        }
        // Route through the invariant (#1696): hiding the last visible pane is
        // refused, so the content area is never left empty.
        setPaneVisible(.canvas, isVisible)
    }

    func setReadingPaneVisible(_ isVisible: Bool) {
        if isVisible {
            currentLayoutMode = .widescreen
            viewSettings.previewMode = .widescreen
        }
        setPaneVisible(.reading, isVisible)
    }

    /// Chat is auxiliary (never the last content pane), so unlike
    /// preview/reading it toggles directly — no #1696 invariant to guard.
    func setChatPaneVisible(_ isVisible: Bool) {
        if isVisible {
            currentLayoutMode = .widescreen
            viewSettings.previewMode = .widescreen
        }
        showChatPane = isVisible
    }

    /// Show/hide the library list pane beside the reader (#4288). Unlike the
    /// preview/reading toggles this does NOT force widescreen: collapsing the
    /// list is a "focus on reading" gesture, so the current layout mode stays as
    /// the user left it and the ≥1-visible-pane invariant does the rest.
    func setLibraryPaneVisible(_ isVisible: Bool) {
        setPaneVisible(.grid, isVisible)
    }

    /// Summon/dismiss the engine-search field in the library's mini toolbar
    /// (#4521). Dismissing exits transient-search presentation through the ONE
    /// existing path (`clearTransientSearch`, #4106/S2 semantics unchanged)
    /// and empties the field — otherwise hiding the chrome would leave the
    /// library silently showing results for a query nobody can see.
    func setSearchFieldVisible(_ isVisible: Bool) {
        showSearchField = isVisible
        guard !isVisible else { return }
        toolbarSearchText = ""
        if activeSearchQuery != nil {
            clearTransientSearch()
        }
    }

    func openChatWithCurrentScope() {
        // Follow-up (#1723): keep this discoverable sidebar entry, but promote the
        // scoped-docs chat into a first-class inspector pane/tab once the
        // library inspector gets a stable chat slot.
        let scopedIds = ChatScopeBuilder.currentScopeDocumentIds(
            browserSelection: browserSelection,
            currentDocuments: documentStore.currentDocuments,
            detailDocument: detailDocument
        )
        let route = ChatWithDocsRouter.mainChatRoute(documentIds: scopedIds)
        chatSelectedDocuments = route.selectedDocumentIds
        sidebarMode = route.sidebarMode
        viewMode = route.viewMode
    }
}
