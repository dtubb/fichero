import SwiftUI
// `UTType` for the content-pane drop's `.item` root type — a split file
// inherits symbols, not imports (#4353).
import UniformTypeIdentifiers

// MARK: - ContentView Root Layout Extension
// Agent: ViewBuilderAgent
// Responsibility: The top-level main-content composition (NavigationSplitView +
// inspector + immersive reading overlay) that `body` mounts. Split out of
// ContentView.swift to keep it under the file_length limit; `body` itself and
// all @State/@Environment stored properties stay in ContentView.swift.

extension ContentView {
    /// Main app content (when backend is connected)
    /// Internal (not private): referenced from `body` in ContentView.swift —
    /// `private` is file-scoped.
    @ViewBuilder
    var mainContentView: some View {
        let inspectorIsPresented = Binding(
            get: { effectiveShowInspectorSidebar },
            set: { showInspectorSidebar = $0 }
        )
        // Inspector is a NATIVE SwiftUI `.inspector()` column attached to the
        // NavigationSplitView, so it persists across all view modes (#1199) AND
        // the unified window toolbar/title spans it correctly — trailing toolbar
        // items sit above the inspector instead of the toolbar overrunning it
        // (#2033). It replaced the former window-level HStack sibling, which
        // macOS painted the toolbar across (the bug the user hit).
        //
        // The split-view column itself carries a very long chained-modifier
        // list (toolbar + ~16 .onChange/.onReceive handlers). To keep any single
        // `some View` expression inside the Swift type-checker's complexity
        // budget, that chain is broken across THREE intermediate properties:
        // `navigationSplitColumn` (NavigationSplitView + first modifiers),
        // `decoratedNavigationSplitColumn` (selection/visibility handlers), and
        // `requestBusesAndAppleScript` (request buses + AppleScript receivers).
        // The third split was forced by iOS, whose type-checker budget is
        // tighter than macOS's: two segments compiled on Mac and timed out the
        // iOS archive.
        requestBusesAndAppleScript
            .adaptiveInspector(placement: inspectorPlacement, isPresented: inspectorIsPresented) {
                inspectorContainerView
            }
            // Measure the real container width before the outer min-width
            // clamp, otherwise the reader only ever sees the framed width.
            .background(windowWidthReader)
            .frame(
                minWidth: CGFloat(shellWindowMinWidth),
                maxWidth: .infinity,
                maxHeight: .infinity
            )
            // The legacy compact inspector popover was removed (#2812): it fired
            // on the same compact selection that already pushes the reader, so
            // selection presented the reader AND a popover at once. At compact
            // the adaptive inspector routes to `.navigationPush`
            // (InspectorPresenter), opened by the explicit Info button — one
            // presentation, not two.

        // Distraction-free full-window reading (#2520). Top-level overlay so it
        // covers sidebar, inspector, and toolbar; ⌥⌘F enters, Esc exits.
        .overlay { immersiveReadingOverlay }
        .background {
            Button("Enter Full-Screen Reading", action: enterImmersiveReading)
                .keyboardShortcut("f", modifiers: [.command, .option])
                .opacity(0)
                .disabled(immersiveReadingDocument == nil)
        }
    }

    private var immersiveReadingDocument: Document? {
        pageFocusDocument ?? detailDocument
    }

    @ViewBuilder
    private var immersiveReadingOverlay: some View {
        if isImmersiveReading, let doc = immersiveReadingDocument {
            ImmersiveReaderView(
                document: doc,
                isPresented: $isImmersiveReading,
                siblings: documentStore.currentDocuments.filter {
                    $0.fileType == .image || $0.docType == .page
                },
                onNavigate: { detailDocument = $0 }
            )
            .transition(.opacity)
        }
    }

    private func enterImmersiveReading() {
        guard immersiveReadingDocument != nil else { return }
        isImmersiveReading = true
    }

    @ViewBuilder
    private var windowWidthReader: some View {
        GeometryReader { geo in
            Color.clear
                .onAppear {
                    handleWindowWidthChange(geo.size.width)
                }
                .onChange(of: geo.size.width) { _, newWidth in
                    handleWindowWidthChange(newWidth)
                }
        }
    }

    /// The NavigationSplitView detail column (centerContent + its modifiers).
    /// Extracted from `navigationSplitColumn` so neither `some View` expression
    /// exceeds the Swift type-checker's complexity budget (#"unable to type-check
    /// this expression in reasonable time").
    @ViewBuilder
    private var detailColumn: some View {
        detailShellColumn
            .toolbar { detailToolbarContent }
            // The content-pane external drop (#4184), scoped to `detailColumn`
            // specifically — never the sidebar. Scope was the ONLY reason
            // #4184's `.onDrop` was reverted: it had been applied to the whole
            // `NavigationSplitView`, so nobody could rule out its stealing
            // hit-testing from nested sidebar rows. Here the sidebar is not
            // inside the modified view at all, so that argument does not apply.
            //
            // This replaces the #4458 `ContentDropTargetView` AppKit bridge,
            // which could not work: `NSItemProvider` does not conform to
            // `NSPasteboardReading`, so its
            // `readObjects(forClasses: [NSItemProvider.self])` never returned
            // providers — and its load-bearing `hitTest -> nil` override is
            // exactly how AppKit's drag-destination search fails to find a
            // view, since that search walks `hitTest` too. Both defects are
            // provable from the API contract; neither needed a live drag.
            //
            // `.item` is UTType's root, so this accepts the content-UTI drags
            // (Mail, Safari, in-progress downloads) that a `.fileURL`-only
            // destination silently discarded. A folder cell's own
            // `.dropDestination` sits inside this view and keeps first claim —
            // SwiftUI resolves drops innermost-first, the same way the sidebar
            // rows' nested handlers already work.
            // `isTargeted:` is required to select the closure overload —
            // without it Swift matches `.onDrop(of:delegate:)` and rejects the
            // trailing closure.
            .onDrop(of: [.item], isTargeted: nil) { providers in
                handleContentPaneExternalDrop(providers)
                return true
            }
            // The detail column carries only a MODEST hard floor — the
            // always-present library-list spine width — NOT the full
            // per-layout `paneAwareDetailMinWidth`. The full content
            // reservation lives on the window-min frame in `mainContentView`
            // (sidebar + detail). Pinning the FULL detail min here made
            // NavigationSplitView sacrifice the SIDEBAR (whose column min
            // yields first under pressure) whenever the window narrowed below
            // sidebar+detail — the sidebar collapsed/disappeared. With a small
            // floor the sidebar always keeps its `.navigationSplitViewColumnWidth`
            // min and the CONTENT shrinks/scrolls instead (frame ① bug-fix).
            .frame(minWidth: CGFloat(ContentView.contentListMinWidth), maxWidth: .infinity)
            // Publish the per-window inspector binding from the detail
            // column (always present) rather than the sidebar, which leaves
            // the hierarchy when collapsed and made ⌘⌥I no-op (#1513/#1451).
            .focusedSceneValue(\.showInspector, $showInspectorSidebar)
            // Publish the reading-surface pane toggles so the View menu can
            // mirror the toolbar buttons for each pane (#1215).
            // Route every pane toggle through the invariant (#1696) so the View
            // menu can't hide the last visible pane. Storage stays @SceneStorage.
            .focusedSceneValue(\.showDocumentGrid, paneBinding(.grid))
            .focusedSceneValue(\.showDocumentCanvas, paneBinding(.canvas))
            .focusedSceneValue(\.showReadingPane, paneBinding(.reading))
            .focusedSceneValue(
                \.navigationUndoAction,
                FocusedLibraryAction(isEnabled: navigationHistory.canGoBack, run: navigateBack)
            )
            // Back/Forward menu items (#3581) — own focused values so they don't
            // ride the ⌘Z fallback; per-window scope matches the toolbar buttons.
            .focusedSceneValue(
                \.navigateBackAction,
                FocusedLibraryAction(isEnabled: navigationHistory.canGoBack, run: navigateBack)
            )
            .focusedSceneValue(
                \.navigateForwardAction,
                FocusedLibraryAction(isEnabled: navigationHistory.canGoForward, run: navigateForward)
            )
    }

    /// NavigationSplitView + the FIRST half of its modifier chain.
    /// Split out of `mainContentView` so no single `some View` expression
    /// exceeds the Swift type-checker's complexity budget (#"unable to
    /// type-check this expression in reasonable time").
    @ViewBuilder
    private var navigationSplitColumn: some View {
        NavigationSplitView(
            columnVisibility: $columnVisibility,
            preferredCompactColumn: $preferredCompactColumn
        ) {
            sidebarContent
        } detail: {
            detailColumn
        }
        // Force DISJOINT, side-by-side columns (#3069): the default `.automatic`
        // style can fall back to an OVERLAID sidebar on macOS that draws on top
        // of the content/library list and clips its leading edge. `.balanced`
        // keeps the sidebar as a real column beside the content, fully visible.
        .navigationSplitViewStyle(.balanced)
        .navigationTitle(toolbarTitle)
        // The breadcrumb subtitle is a desktop window-title affordance; on a
        // compact iPhone nav bar it reads as duplicate path text, so drop it
        // there and let the single inline title stand (#2814).
        .modifier(NavigationSubtitleCompat(
            subtitle: horizontalSizeClass == .compact ? "" : breadcrumbSubtitle
        ))
        // The search field moved into the library's mini toolbar (#4407).
        // `.searchable` attaches to a NAVIGATION CONTAINER, and this one was on
        // the whole `NavigationSplitView` — so `.searchScopes` drew the
        // Ask/Keyword selector as a bar spanning the library, the preview and
        // the reader together. A control whose placement claimed window scope
        // while it filtered one list. See `LibraryView+MiniToolbar`.
        // Clearing the field (or its ⓧ) exits transient-search presentation
        // and restores the browsed folder's contents (#4106/S2).
        .onChange(of: toolbarSearchText) { _, newText in
            if newText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                activeSearchQuery != nil {
                clearTransientSearch()
            }
        }
        .onAppear {
            handleOnAppear()
            syncFocusedDocumentSelection(detailDocument)
        }
        .onChange(of: documentStore.collections) { old, new in
            handleCollectionsChange(old: old, new: new)
        }
        .onChange(of: documentStore.currentDocuments) { _, newDocs in
            handleCurrentDocumentsChange(newDocs)
        }
        // Change-stream splices for page children land in childrenCache /
        // collections, not currentDocuments — refresh the focused snapshots
        // from the store's full-container lookup too (#4318).
        .onChange(of: documentStore.revision) { _, _ in
            handleDocumentRevisionChange()
        }
        // Inspector visibility is per-window (@SceneStorage). It is NOT mirrored
        // into the app-wide ViewSettings any more — doing so flipped the
        // inspector in every open window at once (#1451). The View menu reaches
        // this window's state through FocusedValues.showInspector instead.
        .onChange(of: showInspectorSidebar) { _, _ in
            updateColumnVisibility()
        }
        .toolbar { mainToolbarContent }
        .onChange(of: viewSettings.previewMode) { _, newPreviewMode in
            handlePreviewModeChange(newPreviewMode)
        }
        .onChange(of: viewSettings.libraryLayout) { _, newLibraryLayout in
            handleLibraryLayoutChange(newLibraryLayout)
        }
        .onChange(of: viewMode) { oldMode, newMode in
            handleViewModeChange(old: oldMode, new: newMode)
        }
    }

    /// `navigationSplitColumn` + the SECOND half of the modifier chain.
    /// See `navigationSplitColumn` for why the chain is split.
    @ViewBuilder
    private var decoratedNavigationSplitColumn: some View {
        navigationSplitColumn
            .onChange(of: sidebarSelectionState.selectedItemId) { _, newFolderId in
                selectedSidebarItemId = newFolderId
                handleSidebarSelectionChange(newFolderId)
            }
            .onChange(of: sidebarMode) { _, _ in
                handleSidebarModeChange()
            }
            .onChange(of: showSidebar) { _, _ in
                updateColumnVisibility()
            }
            .onChange(of: columnVisibility) { _, newVisibility in
                handleColumnVisibilityChange(newVisibility)
            }
            .onChange(of: browserSelection) { _, newSelection in
                handleBrowserSelectionChange(newSelection)
            }
            .onChange(of: detailDocument) { _, newDoc in
                syncFocusedDocumentSelection(newDoc)
                handleDetailDocumentChange(newDoc)
            }
            // #4518: the ONE teardown for "this window now shows a different
            // library" — closing a library falls back to Global, and nothing
            // else clears the per-document snapshots, so Preview/Reader/
            // Inspector kept rendering "empty for THIS document" states for a
            // document belonging to nothing.
            .onChange(of: windowState.libraryId) { _, _ in
                handleLibraryChange()
            }
            #if canImport(AppKit)
            .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
                handleWillTerminate()
            }
            #else
            // iOS/iPadOS have no willTerminate — the system can suspend then kill
            // a backgrounded app with no further callback. Backgrounding is the
            // last reliable save point, so mirror the macOS terminate path (#3016).
            // @SceneStorage nav/selection persist automatically; this covers the
            // editing-workflow autosave that handleWillTerminate() performs.
            .onChange(of: scenePhase) { _, newPhase in
                if newPhase == .background {
                    handleWillTerminate()
                }
            }
            #endif
    }

    /// The THIRD segment of the chain, split for the same reason as the second:
    /// iOS's type-checker budget is tighter than macOS's, and the combined
    /// chain compiled on macOS while timing out the iOS archive with
    /// "unable to type-check this expression in reasonable time". Each split is
    /// a compile-time bound, not a stylistic one — do not recombine them.
    @ViewBuilder
    private var requestBusesAndAppleScript: some View {
        decoratedNavigationSplitColumn
            .onChange(of: entitySearchState.requestID) { _, _ in
                handleEntitySearchRequested()
            }
            .onChange(of: claimSourceNavigationState.requestID) { _, _ in
                handleOpenClaimSource()
            }
            // #4373: a reader page click routes through the SAME selection path
            // a sidebar click uses, so the sidebar, preview and inspector all
            // update as observers rather than through a parallel navigation.
            .onChange(of: readerPageActivationState.requestID) { _, _ in
                handleReaderPageActivated()
            }
            // Scope both request buses to this window's subtree (#3437).
            .environment(entitySearchState)
            .environment(claimSourceNavigationState)
            .environment(readerPageActivationState)
            .environment(activeSurfaceState)
            .onReceive(NotificationCenter.default.publisher(for: .ficheroSelectDocumentRequested)) { note in
                handleAppleScriptSelectDocument(note)
            }
            .onReceive(NotificationCenter.default.publisher(for: .ficheroShowPanelRequested)) { note in
                handleAppleScriptShowPanel(note)
            }
            .onChange(of: kgFocusState.sourceDocumentId) { _, _ in
                handleKGFocusChanged()
            }
            .onChange(of: kgFocusState.sourcePageLabel) { _, _ in
                handleKGFocusChanged()
            }
            // "Show in Graph" from the inspector switches to the Knowledge Graph
            // force graph, focused on the requested entity (#3452). The focus is
            // already set by requestGraphReveal; we just flip the mode.
            .onChange(of: kgFocusState.graphRevealRequestToken) { _, _ in
                sidebarMode = .knowledgeGraph
            }
            .onChange(of: viewDisplayMode) { _, newMode in
                handleViewDisplayModeChange(newMode)
            }
            .onChange(of: workflowStore.changeToken) { _, _ in
                workflowReloadTask?.cancel()
                workflowReloadTask = Task {
                    try? await Task.sleep(for: .milliseconds(300))
                    guard !Task.isCancelled else { return }
                    await workflowStore.loadWorkflows()
                }
            }
            .modifier(
                MainContentModifiers(
                    documentStore: documentStore,
                    workflowStore: workflowStore,
                    conversationService: conversationService,
                    savedSearchService: savedSearchService,
                    appState: appState,
                    sidebarMode: $sidebarMode,
                    viewMode: $viewMode,
                    browserSelection: $browserSelection,
                    detailDocument: $detailDocument,
                    columnVisibility: $columnVisibility,
                    editingWorkflow: $editingWorkflow,
                    currentLayoutMode: $currentLayoutMode,
                    isDropTargeted: $isDropTargeted,
                    isImporting: $isImporting,
                    importProgress: $importProgress,
                    importError: $importError,
                    handleDocumentChange: handleDocumentChange,
                    handleProviderDrop: handleContentPaneExternalDrop
                )
            )
    }
}

// MARK: - Platform compat

/// `.navigationSubtitle` is unavailable in visionOS. This applies it on the
/// platforms that support it (macOS/iOS) and is a no-op on visionOS, so the
/// window-title breadcrumb (#2425) compiles for every target.
private struct NavigationSubtitleCompat: ViewModifier {
    let subtitle: String
    func body(content: Content) -> some View {
        #if os(visionOS)
        content
        #else
        content.navigationSubtitle(subtitle)
        #endif
    }
}

/// Adds a native `.searchable` field + inline title at compact width (iPhone),
/// where the Mac-style principal breadcrumb + fixed-width search field are
/// dropped (#2814). A no-op elsewhere, so macOS/iPad-regular keep the principal
/// search field.
/// Native toolbar search for every width/platform (#3037), replacing the
/// hand-rolled fixed-220 principal-zone TextField. `.automatic` placement lets
/// the system site it: macOS + iPad-regular put it in the toolbar; iPhone/compact
/// gets the nav-bar search bar for free. Only the compact inline-title tweak is
/// platform-gated.
/// The search field's mode (#4117): plain-language "Ask" (LLM compiles the
/// retrieval) vs literal "Keyword". A native search scope, not extra chrome.
enum SearchFieldMode: String, CaseIterable, Hashable {
    case ask
    case keyword
}

// `ToolbarSearchableModifier` is DELETED (#4407). It applied `.searchable` +
// `.searchScopes` to the whole `NavigationSplitView`, which is why the
// Ask/Keyword selector rendered as a bar across the library, the preview and
// the reader. The search field now lives in the library's own mini toolbar —
// see `LibraryView+MiniToolbar`. Left as a comment rather than deleted
// silently: this is where the next person will look for the window search.
