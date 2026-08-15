import SwiftUI

// MARK: - ContentView Sidebar/Center Layout Extension
// Agent: ViewBuilderAgent
// Responsibility: Sidebar content and center-content layout routing, split out of
// ContentView+ViewBuilders.swift to keep each file under the file_length limit.

extension ContentView {
    // internal (not private): PaneSpec.swift derives the library pane's
    // fixed width from it — `private` in Swift is FILE-scoped.
    var clampedWidescreenContentPaneWidth: CGFloat {
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
        // Reads the HINT, not FocusState — see paneFocusHint's doc comment.
        FadingFocusBorder(isActive: paneFocusHint == pane)
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
                        // Views audit B3: no geometry write-back while a
                        // divider drag is invalidating layout every frame.
                        guard !dividerDragInFlight else { return }
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
                .frame(maxWidth: .infinity)
                .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .content; paneFocusHint = .content })
                .overlay { paneFocusIndicator(for: .content) }
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
                            .frame(maxWidth: .infinity)
                            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .content; paneFocusHint = .content })
                            .overlay { paneFocusIndicator(for: .content) }
                    } else {
                        // Grid hidden (#616): show only the preview/editor at full width.
                        previewView
                            .frame(maxWidth: .infinity)
                            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
                            .overlay { paneFocusIndicator(for: .preview) }
                    }

                case .standard:
                    if showDocumentGrid {
                        PlatformVSplitView {
                            contentWithOptionalModeRail
                                .frame(minHeight: 150, idealHeight: 180)
                                .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .content; paneFocusHint = .content })
                                .overlay { paneFocusIndicator(for: .content) }

                            previewView
                                .frame(minHeight: 400, idealHeight: 720)
                                .overlay { paneFocusIndicator(for: .preview) }
                        }
                        .frame(maxWidth: .infinity)
                    } else {
                        previewView
                            .frame(maxWidth: .infinity)
                            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
                            .overlay { paneFocusIndicator(for: .preview) }
                    }

                case .widescreen:
                    // Library/list, document canvas, and reading/WebKit are
                    // independently toggleable per-window (#1448). The row is
                    // rendered from a PANE LIST now (pane system step 1, #13):
                    // same panes, same sizing, same dividers — see PaneSpec —
                    // but each pane is erased at its own boundary instead of
                    // multiplying into one composed generic (the #4331 class),
                    // and chat/terminal later arrive by adding specs, not
                    // branches.
                    widescreenPaneRow
                }
            }
            .animation(.easeInOut(duration: 0.18), value: layout)
        }
    }
}
