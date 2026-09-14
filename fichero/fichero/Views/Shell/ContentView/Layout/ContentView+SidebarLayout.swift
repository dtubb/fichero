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

    // NOTE: panes draw NO focus ring (ruling 2026-08-31). The fading accent
    // border appeared and vanished inconsistently and often framed the wrong
    // edge, so `FadingFocusBorder` and its `paneFocusIndicator(for:)` helper
    // were deleted outright. Focus TRACKING stays: `focusedPane` /
    // `paneFocusHint` still feed `\.focusedPaneKind`, which ⌘A routing and the
    // focused-command menus depend on. Do not re-add a drawn border here.

    // MARK: - Sidebar

    @ViewBuilder
    var sidebarContent: some View {
        VStack(spacing: 0) {
            sidebarTree
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            // Chat lives BELOW the folder tree (spec panes.chat.below-sidebar):
            // the assistant chat is no longer a centre pane. Gated on the SAME
            // `showChatPane` the sparkles toolbar toggle drives; the divider
            // remembers its height per window. It mounts the SAME `ChatView` the
            // centre pane used (`chatSurface`), so conversation history — which
            // lives in the backend via ChatService/ConversationService, not view
            // @State — is unchanged. Those services (plus WorkspaceStore) are
            // re-injected FROM THE WINDOW'S LIBRARY REFERENCE across this column
            // boundary — the #4513 rule: a missing @Environment object is a hard
            // crash, and re-deriving from `library` (like the inspector boundary
            // does) avoids adding an unconditional @Environment read to
            // ContentView that would trap when no chat is shown.
            if showChatPane,
               let library = libraryManager.getLibrary(id: windowState.libraryId) {
                ResizableDivider(
                    width: $sidebarChatHeight,
                    minWidth: 140,
                    maxWidth: 700,
                    edge: .trailing,
                    axis: .vertical
                )
                chatSurface
                    .frame(height: CGFloat(sidebarChatHeight))
                    .frame(maxWidth: .infinity)
                    // #4513: a missing @Environment object is a HARD crash, and
                    // ChatView's subtree reads EIGHT services non-optionally
                    // (APIClient, ChatService, ConversationService, DocumentStore,
                    // LibraryManager, ResearchService, ResearchStore,
                    // WorkspaceStore). Re-inject the FULL library list (the ONE
                    // mandated boundary helper — 7 of the 8) rather than a
                    // hand-picked subset that would trap on the next one, plus
                    // LibraryManager (the app singleton libraryServiceEnvironment
                    // does not carry). Same seam the inspector boundary uses.
                    .libraryServiceEnvironment(library)
                    .environment(LibraryManager.shared)
                    // Claim pane focus on click — the SAME gesture-only seam the
                    // centre chat/reading/preview panes use (they set
                    // `focusedPane`/`paneFocusHint` via a tap, never a
                    // `.focused(equals:)` two-way binding, which would fight the
                    // chat composer's own TextField focus). `PaneFocus.chat`
                    // already exists.
                    .simultaneousGesture(
                        TapGesture().onEnded { focusedPane = .chat; paneFocusHint = .chat }
                    )
            }
        }
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

    /// The folder-tree sidebar itself. Extracted from `sidebarContent` so a chat
    /// region can sit BELOW it (spec panes.chat.below-sidebar). Carries the
    /// tree's OWN environment, focus and click-to-focus seams; the column-width
    /// + width-tracking modifiers stay on the enclosing column in
    /// `sidebarContent`, which is the view NavigationSplitView hosts as the
    /// sidebar column.
    @ViewBuilder
    private var sidebarTree: some View {
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
        // macOS inactive-selection (Daniel, 2026-09-06): a selected sidebar row
        // keeps its accent name+icon only while the sidebar is the focused
        // pane, and goes grey when focus is in the library — the mirror of the
        // library's own `isPaneFocused` tint. `paneFocusHint` is the durable
        // half of the pair, exactly as `ContentView+Navigation` reads it for
        // the center pane.
        .environment(\.sidebarPaneActive, focusedPane == .sidebar || paneFocusHint == .sidebar)
        // #4301: never let sidebar content paint outside its column. During
        // collapse the column animates below the content's laid-out width; the
        // List clips itself but the bottom toolbar strip does not, and its
        // overflow was left painted over the content column after collapse.
        .clipped()
        // Make the sidebar focusable so arrow keys navigate the List.
        // (Removing this broke arrow-key navigation — see #560.)
        .focusable()
        .focused($focusedPane, equals: .sidebar)
        .focusEffectDisabled()
        // Claim pane focus on ANY click in the sidebar, the exact mirror of the
        // library's `focusedPane = .content; paneFocusHint = .content` tap seams
        // (centerContentRouting / PaneSpec). Daniel, 2026-09-06: after #581ff147e
        // greyed the sidebar's selection while the library held focus, going BACK
        // to the sidebar left the LIBRARY's selection still accent-tinted — the
        // reverse transition never fired. Root cause: the `.focused` binding above
        // sticks for keyboard/Tab entry but a mouse CLICK on a List row does not
        // move @FocusState, so `focusedPane` stayed `.content` and the library's
        // `isPaneFocused` (focusedPane == .content || paneFocusHint == .content)
        // never dropped. The library forces the flip with an explicit tap gesture;
        // the sidebar had no equivalent. `.simultaneousGesture` composes with the
        // List's own selection click (and the per-row/section fallbacks) without
        // consuming it — the same way it does on the center pane.
        .simultaneousGesture(TapGesture().onEnded { focusedPane = .sidebar; paneFocusHint = .sidebar })
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
                // Clip to the content column so list/grid/table rows never paint
                // past it and bleed under the shell sidebar — the same guard the
                // widescreen library pane already has (spec panes.content-column-
                // under-sidebar; the legacy branches lacked it).
                .clipped()
                .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .content; paneFocusHint = .content })
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
                            .clipped()  // no bleed under the sidebar (see above)
                            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .content; paneFocusHint = .content })
                    } else {
                        // Grid hidden (#616): show only the preview/editor at full width.
                        previewView
                            .frame(maxWidth: .infinity)
                            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
                    }

                case .standard:
                    if showDocumentGrid {
                        PlatformVSplitView {
                            contentWithOptionalModeRail
                                .frame(minHeight: 150, idealHeight: 180)
                                .clipped()  // no bleed under the sidebar (see above)
                                .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .content; paneFocusHint = .content })

                            previewView
                                .frame(minHeight: 400, idealHeight: 720)
                        }
                        .frame(maxWidth: .infinity)
                    } else {
                        previewView
                            .frame(maxWidth: .infinity)
                            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
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
