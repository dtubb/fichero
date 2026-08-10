import SwiftUI

// MARK: - ContentView Sidebar/Center Layout Extension
// Agent: ViewBuilderAgent
// Responsibility: Sidebar content and center-content layout routing, split out of
// ContentView+ViewBuilders.swift to keep each file under the file_length limit.

extension ContentView {
    private var clampedWidescreenContentPaneWidth: CGFloat {
        CGFloat(min(max(widescreenContentPaneWidth, ContentView.contentListMinWidth), 900))
    }

    var effectiveCenterIdealWidth: Double {
        // .inspector() is now a sibling of NavigationSplitView, not nested inside the detail
        // column. The split view gets whatever width the inspector leaves, so the content
        // ideal is the same whether the inspector is shown or hidden.
        max(contentWidth, 600)
    }

    // MARK: - Pane Focus Indicator

    /// Returns a view that shows an accent-colored border when the given pane has keyboard focus,
    /// then fades out after a brief moment (like Tinderbox's focus highlight).
    func paneFocusIndicator(for pane: PaneFocus) -> some View {
        FadingFocusBorder(isActive: focusedPane == pane)
            .allowsHitTesting(false)
    }

    // MARK: - Sidebar

    @ViewBuilder
    var sidebarContent: some View {
        SidebarView(
            sidebarMode: $sidebarMode,
            viewMode: $viewMode,
            selectionState: sidebarSelectionState,
            libraryManager: LibraryManager.shared,
            itemRegistry: itemRegistry,
            apiClient: apiClient,
            windowPersistenceId: sidebarWindowPersistenceId,
            onOpenChatWithCurrentScope: {
                openChatWithCurrentScope()
            },
            onRunSavedSearch: { search in
                runSavedSearch(search)
            },
            onRequestNextPaneFocus: {
                cyclePaneFocus(reverse: false)
            }
        )
        .environment(savedSearchService)
        .environment(conversationService)
        .environment(ErrorService.shared)
        .environment(performanceService)
        // #4301: never let sidebar content paint outside its column. During
        // collapse the column animates below the content's laid-out width; the
        // List clips itself but the bottom toolbar strip does not, and its
        // overflow was left painted over the content column after collapse.
        .clipped()
        .overlay { paneFocusIndicator(for: .sidebar) }
        // Make the sidebar focusable so arrow keys navigate the List.
        // (Removing this broke arrow-key navigation — see #560.)
        .focusable()
        .focused($focusedPane, equals: .sidebar)
        .focusEffectDisabled()
        // Track the column's live rendered width so each mode's @AppStorage
        // ideal is updated when the user drags the divider. The GeometryReader
        // fires on every layout pass — guard with a min-delta to avoid writing
        // on every pixel during animation.
        .background(
            GeometryReader { geo in
                Color.clear
                    .onChange(of: geo.size.width) { _, newWidth in
                        guard newWidth > 0, abs(newWidth - sidebarWidth) > 2 else { return }
                        sidebarWidth = newWidth
                    }
            }
        )
        // min: 180 lets the sidebar collapse tight enough that the mode
        // icons dominate the column with minimal wasted space (#615).
        // Was 250 — felt bloated on small screens.
        //
        .navigationSplitViewColumnWidth(
            min: ContentView.sidebarMinWidth,
            ideal: sidebarWidth,
            max: 600
        )
        .focusedSceneValue(\.sidebarMode, $sidebarMode)
        // NOTE: \.showInspector is published from the detail column in
        // ContentView.navigationSplitColumn (always present), NOT here — the
        // sidebar leaves the hierarchy when collapsed, which disabled ⌘⌥I
        // and the View-menu toggle while the sidebar was hidden (#1513).
        .focusedSceneValue(\.navigateToParentAction, FocusedLibraryAction(isEnabled: true, run: navigateToParent))
    }

    // MARK: - Center Content (with Layout Modes)

    // The library/search view-mode icon rail (`horizontalModeStrip`) that used
    // to sit at the top of the content column was removed (#2032): presentation
    // controls live in the View menu (ViewMenuCommands.LibraryLayoutSection,
    // ⌘1–4), not in a floating in-content icon bar. The mode-switch state is
    // unchanged — the View menu still drives `viewSettings.libraryLayout`.
    @ViewBuilder
    var contentWithOptionalModeRail: some View {
        // Was the publish point for the View menu's 3D "Space" (.realitykit)
        // button via @FocusedValue; that button and its FocusedValues were
        // retired with the Mind Palace renderer. Now a plain passthrough — the
        // toolbar picker drives viewDisplayMode directly.
        contentView
    }

    @ViewBuilder
    var centerContent: some View {
        // The location breadcrumb lives ONLY in the window toolbar's principal
        // lozenge — the pane-level clickable strip (#1928) was one of FOUR
        // in-window copies of the same path and is retired (#4102 dedupe).
        centerContentRouting
    }

    @ViewBuilder
    private var centerContentRouting: some View {
        // COMPACT (iPhone/iOS) — Overcast-style forward navigation (#2551).
        // The library/search LIST is the root of a NavigationStack; tapping a
        // leaf document PUSHES the reader (the SAME EditorView the regular
        // content pane shows in its preview slot) with a Back button to return.
        // The macOS/iPad-regular split path is the `else` chain below and is
        // UNCHANGED — `usesCompactReaderFlow` is compile-time `false` on macOS
        // (shouldUseCompactNavigationFlow) and only ever true at compact width.
        if usesCompactReaderFlow {
            compactLibraryReaderStack
        } else if !showsPreviewPane {
            // Non-library/search modes (activity, workflows, chat, etc.) never use
            // the preview split — they own the full content area themselves.
            contentWithOptionalModeRail
                .overlay { paneFocusIndicator(for: .content) }
                .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .content })
                .frame(maxWidth: .infinity)
        } else {
            // Folders now show the current layout so the WebKit/reading
            // pane remains visible for folder-level aggregate content (#1405).
            let layout: LayoutMode = currentLayoutMode
            // Group + .animation gives SwiftUI a stable outer identity so the
            // first .none → .standard/.widescreen transition (when the user
            // first activates a doc from full-grid) animates smoothly instead
            // of remounting + flashing every grid cell. (#770/#778 follow-up)
            Group {
                switch layout {
                case .none:
                    if showDocumentGrid {
                        contentWithOptionalModeRail
                            .overlay { paneFocusIndicator(for: .content) }
                .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .content })
                            .frame(maxWidth: .infinity)
                    } else {
                        // Grid hidden (#616): show only the preview/editor at full width.
                        previewView
                            .overlay { paneFocusIndicator(for: .preview) }
                            .frame(maxWidth: .infinity)
                    }

                case .standard:
                    if showDocumentGrid {
                        PlatformVSplitView {
                            contentWithOptionalModeRail
                                .overlay { paneFocusIndicator(for: .content) }
                .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .content })
                                .frame(minHeight: 150, idealHeight: 180)

                            previewView
                                .overlay { paneFocusIndicator(for: .preview) }
                                .frame(minHeight: 400, idealHeight: 720)
                        }
                        .frame(maxWidth: .infinity)
                    } else {
                        previewView
                            .overlay { paneFocusIndicator(for: .preview) }
                            .frame(maxWidth: .infinity)
                    }

                case .widescreen:
                    // Library/list, document canvas, and reading/WebKit are
                    // independently toggleable per-window (#1448). Hiding the
                    // Library pane must not collapse the reading workspace into
                    // a different single-preview layout.
                    let panePlan = adaptiveWidescreenPanePlan
                    HStack(spacing: 0) {
                        if panePlan.showsLibraryPane {
                            // When both reading panes are hidden the list takes the
                            // whole width instead of staying a fixed column with a
                            // blank grey area beside it (#1516). list-only is a valid
                            // state — the library list is the always-present spine.
                            // list-only is full-width. `width: .infinity` is an invalid
                            // frame dimension (SwiftUI logs "Invalid frame dimension
                            // (negative or non-finite)" #2006) — flex with maxWidth
                            // instead, and pin a fixed width only when a reading pane
                            // shares the row.
                            let widescreenContentFixedWidth: CGFloat? =
                                (panePlan.showsCanvasPane || panePlan.showsReadingPane)
                                    ? clampedWidescreenContentPaneWidth : nil
                            // Splittable (h/v) Library list pane — #2276.
                            adaptiveSplittablePane(storageKey: "library") {
                                contentWithOptionalModeRail
                            }
                            .overlay { paneFocusIndicator(for: .content) }
                .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .content })
                            .frame(width: widescreenContentFixedWidth)
                            .frame(maxWidth: widescreenContentFixedWidth == nil ? .infinity : nil)
                            // The library pane must never paint past its own split
                            // column — otherwise list/grid rows can bleed under the
                            // shell sidebar or off the left window edge.
                            .clipped()
                        }

                        if panePlan.showsLibraryDivider {
                            ResizableDivider(
                                width: $widescreenContentPaneWidth,
                                minWidth: ContentView.contentListMinWidth,
                                maxWidth: 900,
                                edge: .leading
                            )
                        }

                        if panePlan.showsCanvasPane {
                            widescreenCanvasPane

                            if panePlan.showsCanvasReadingDivider {
                                ResizableDivider(
                                    width: $pageContentPaneWidth,
                                    minWidth: ContentView.readingPaneMinWidth,
                                    maxWidth: 900,
                                    edge: .trailing
                                )
                                widescreenReadingPane
                                    .frame(width: CGFloat(pageContentPaneWidth))
                            }
                        } else if panePlan.showsReadingPane {
                            widescreenReadingPane
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .frame(maxWidth: .infinity)
                }
            }
            .animation(.easeInOut(duration: 0.18), value: layout)
        }
    }
}
