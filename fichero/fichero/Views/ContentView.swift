import OSLog
import SwiftUI
import UniformTypeIdentifiers

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ContentView")
// swiftlint:disable file_length

/// Identifies which main pane has keyboard focus for Tab cycling
enum PaneFocus: Hashable {
    case sidebar, content, preview, reading, inspector
}

// Main content view with three-column navigation
// Switches between Library, Search, and Workflow views based on sidebar selection
//
// Architecture: This view has been refactored into multiple extensions for maintainability:
// - ContentView+State: Computed properties and state helpers
// - ContentView+ViewBuilders: View builders for sidebar, content, preview, inspector
// - ContentView+Navigation: Content routing based on AppViewMode
// - ContentView+Actions: Action handlers and business logic
// - ContentView+Persistence: State serialization for @SceneStorage
// swiftlint:disable:next type_body_length
struct ContentView: View {
    #if os(macOS)
    static let defaultColumnVisibility: NavigationSplitViewVisibility = .all
    static let defaultColumnVisibilityRaw: Int = 2 // .all
    #else
    static let defaultColumnVisibility: NavigationSplitViewVisibility = .detailOnly
    static let defaultColumnVisibilityRaw: Int = 1 // .detailOnly
    #endif
    /// Column the split view roots at when collapsed on compact width
    /// (#2329/#2334). `.detail` lands compact width on the library/search
    /// workspace so iPhone starts in the one-view-at-a-time flow instead of
    /// the folder tree.
    static let defaultPreferredCompactColumn: NavigationSplitViewColumn = .detail
    static let sidebarMinWidth: Double = 160
    static let inspectorMinWidth: Double = 220
    static let inspectorMaxWidth: Double = 420
    static let contentMinWidth: Double = 520
    static let contentMaxWidth: Double = 2200
    /// Minimum width of the widescreen content-list pane. Clamped to the
    /// view-mode icon rail width so the rail and list rows (thumbnail + text)
    /// can't be dragged narrow enough to clip (#1243). The sort/filter tools
    /// now overflow into a trailing menu when the rail gets tight (#1733), so
    /// the list can shrink far enough to let the adaptive thumbnail grid fall
    /// to a single column again (#1734).
    nonisolated static let contentListMinWidth: Double = 220
    /// Minimum width of the flexible PDF canvas pane so its mini-toolbar
    /// (zoom −/%/+, fit, actual-size, magnifier, loupe + two dividers) never
    /// clips when the reading-surface dividers are dragged inward. The
    /// resizable neighbours are already clamped by their ResizableDividers;
    /// this guards the one `.frame(maxWidth: .infinity)` pane that otherwise
    /// has no floor. (#1454)
    nonisolated static let pdfCanvasMinWidth: Double = 360
    nonisolated static let readingPaneMinWidth: Double = 220

    // MARK: - Environment

    @EnvironmentObject var viewSettings: ViewSettings
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var apiClient: APIClient
    @Environment(DocumentStore.self) var documentStore: DocumentStore
    @EnvironmentObject var conversationService: ConversationServiceGenerated
    @EnvironmentObject var importService: ImportServiceGenerated
    @EnvironmentObject var windowState: WindowState
    @Environment(WorkflowStore.self) var workflowStore
    @EnvironmentObject var savedSearchService: SavedSearchServiceGenerated
    @EnvironmentObject var workflowStreamService: WorkflowStreamService
    @Environment(WorkflowExecutionObserver.self) var executionObserver
    @Environment(KGFocusState.self) var kgFocusState
    @Environment(\.horizontalSizeClass) var horizontalSizeClass
    @Environment(\.openWindow) var openWindow
    @EnvironmentObject var claimFocusState: ClaimFocusState
    @EnvironmentObject var researchService: ResearchService

    // MARK: - State (synced with @SceneStorage for persistence)

    // Runtime state - full objects for use in views
    @State var viewMode: AppViewMode = .library(nil)
    @State var detailDocument: Document?
    @State private var focusedDocument = FocusedDocument.shared
    /// The page document currently in view, updated only by scroll/page-flip
    /// events. Drives the inspector without re-rooting the WebKit pane (#1463).
    @State var pageFocusDocument: Document?
    @State var columnVisibility: NavigationSplitViewVisibility = ContentView.defaultColumnVisibility
    /// Which column the split view roots at when it COLLAPSES to a stack on
    /// compact width (#2329/#2334). `.detail` lands a phone on the document
    /// list/reader, with the sidebar (folder tree + library picker) one
    /// swipe-back away. Inert at regular width / macOS, where the split never
    /// collapses. SwiftUI mutates this as the user navigates the stack.
    @State var preferredCompactColumn: NavigationSplitViewColumn = ContentView.defaultPreferredCompactColumn
    @State var browserSelection: Set<String> = []
    @State var sidebarSelectionState = SidebarSelectionState()

    // Persisted state (@SceneStorage) - synced via .onAppear and .onChange
    @SceneStorage("selectedSidebarItem") var selectedSidebarItemId: String?
    @SceneStorage("columnVisibilityRaw") var columnVisibilityRaw: Int = ContentView.defaultColumnVisibilityRaw
    @SceneStorage("browserSelectionData") var browserSelectionData: Data = Data()
    @SceneStorage("viewModeType") var storedViewModeType: String = "library"
    @SceneStorage("viewModeItemId") var storedViewModeItemId: String?

    // Workflow state
    @State var editingWorkflow: Workflow = Workflow(name: "New Workflow", description: "")
    @State private var workflowReloadTask: Task<Void, Never>?

    // Chat state (shared between ChatView and ChatInspectorView)
    @State var chatSelectedDocuments: Set<String> = []

    /// The leaf document currently PUSHED in the compact (iPhone) reader stack
    /// (#2666). Backed by real @State — not a computed Binding — so
    /// `.navigationDestination(item:)` reliably fires the push when the selection
    /// resolves to a leaf, even if `selectedDocuments` and `currentDocuments`
    /// momentarily disagree. Synced from selection by `syncPushedReaderDocument()`.
    @State var pushedReaderDocument: Document?

    // Main toolbar state (per-window persistence)
    @SceneStorage("viewDisplayMode") var viewDisplayMode: ViewDisplayMode = .icon

    /// Global default — survives window close, fresh launches, even
    /// when no per-folder override exists. Solves the "set List, switch
    /// items, reverts to Icon" complaint in #943. Synced with
    /// viewDisplayMode every time the user changes view mode via
    /// updateViewDisplayMode; consulted as the fallback when neither
    /// SceneStorage nor a per-folder save has a value.
    @AppStorage("library.defaultViewDisplayMode")
    var defaultLibraryViewDisplayMode: ViewDisplayMode = .icon
    @SceneStorage("currentLayoutMode") var currentLayoutMode: LayoutMode = .widescreen
    @SceneStorage("sidebarMode") var sidebarMode: SidebarMode = .library

    // Column visibility persistence
    @AppStorage("sidebarWidth") var sidebarWidth: Double = 280
    @AppStorage("contentWidth") var contentWidth: Double = 600
    @AppStorage("inspectorWidth") var inspectorWidth: Double = 300
    @AppStorage("widescreenContentPaneWidth") var widescreenContentPaneWidth: Double = 320
    @AppStorage("pageListWidth") var pageListWidth: Double = 120
    @AppStorage("pageContentPaneWidth") var pageContentPaneWidth: Double = 200
    @SceneStorage("showSidebar") var showSidebar: Bool = true
    @SceneStorage("showInspectorSidebar") var showInspectorSidebar: Bool = true
    @SceneStorage("showDocumentGrid") var showDocumentGrid: Bool = true
    // Per-window visibility of the three middle panes (#1448). Each window
    // keeps its own choice via @SceneStorage (same pattern as the
    // sidebar/inspector toggles), so selection never remounts or hides panes.
    @SceneStorage("showDocumentCanvas") var showDocumentCanvas: Bool = true
    @SceneStorage("showReadingPane") var showReadingPane: Bool = true
    @State var measuredWindowWidth: Double = 0
    // When false (default), selecting a different item NEVER changes which
    // panes are visible — a folder shows the same panes as a PDF. The visible
    // pane set is the user's choice (the toggles above). Opt in to the old
    // selection-driven behaviour (e.g. folders collapse the preview) by
    // turning this on. App-wide preference, toggled from the View menu. (#1452)
    @AppStorage("layout.followsSelection") var layoutFollowsSelection: Bool = false
    // Library sort field / direction / filter-bar visibility, lifted out of
    // LibraryView's @State so the in-content mode rail can host the Sort + Filter
    // controls at the Library view's top-right (#1477).
    @StateObject var libraryToolbarState = LibraryToolbarState()

    // Map view persistence (latitude, longitude, zoom)
    @SceneStorage("mapLatitude") var mapLatitude: Double = 0.0
    @SceneStorage("mapLongitude") var mapLongitude: Double = 0.0
    @SceneStorage("mapZoom") var mapZoom: Double = 1.0
    @SceneStorage("sidebarWindowPersistenceId") var sidebarWindowPersistenceId: String = UUID().uuidString

    // Per-folder view mode persistence (JSON-encoded [folderId: displayMode.rawValue], per-window)
    @SceneStorage("folderViewDisplayModes") var folderViewDisplayModesJSON: String = "{}"

    @StateObject var itemRegistry = ItemTypeRegistry()
    @StateObject var performanceService = PerformanceService()
    @State var documentScrollSync = DocumentScrollSyncState()
    @State var toolbarSearchText: String = ""
    @State var navigationHistory = AppNavigationHistory()
    @State var isRestoringNavigationHistory = false

    // Error service (using singleton pattern)
    @ObservedObject var errorService = ErrorService.shared
    @ObservedObject var featureManager = FeatureManager.shared
    @ObservedObject var workflowRunProviderCache = WorkflowRunProviderCache.shared

    // Pane focus state for Tab cycling
    @FocusState var focusedPane: PaneFocus?

    // NOTE: the toolbar's contextual Delete button was removed. Reading
    // `@FocusedValue(\.libraryDeleteSelection)` HERE (ContentView hosts
    // LibraryView in its detail column) closed an infinite invalidation loop:
    // LibraryView re-allocates that NON-Equatable closure every body pass →
    // republishes the focused value → invalidates this reader → re-renders the
    // detail column → LibraryView body again → ~97% CPU at idle. Re-add Delete
    // to the toolbar only via a STABLE/Equatable focused value (Binding<Bool> or
    // an Equatable action wrapper), never a fresh closure. (#2032 / frame ①)

    // Drag and drop state
    @State var isDropTargeted = false
    @State var isImporting = false
    @State var importProgress: String?
    @State var importError: String?

    // MARK: - Body

    var body: some View {
        Group {
            if appState.isCheckingBackend {
                // Show loading while checking API
                VStack(spacing: 16) {
                    ProgressView()
                        .scaleEffect(1.5)
                    Text("Connecting to backend...")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if !appState.isBackendRunning {
                // API not running - show error
                VStack(spacing: 20) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 64))
                        .foregroundColor(.orange)

                    Text("Backend Not Running")
                        .font(.title)
                        .fontWeight(.bold)

                    Text(appState.backendError ?? "Cannot connect to the Fichero API server.")
                        .multilineTextAlignment(.center)
                        .foregroundColor(.secondary)
                        .frame(maxWidth: 400)

                    HStack(spacing: 16) {
                        Button("Retry") {
                            Task { @MainActor in
                                await appState.checkBackendHealth()
                            }
                        }
                        .keyboardShortcut("r", modifiers: [.command])

                        #if canImport(AppKit)
                        Button("Quit") {
                            NSApplication.shared.terminate(nil)
                        }
                        .keyboardShortcut("q", modifiers: [.command])
                        #endif
                    }
                    .padding(.top, 10)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                mainContentView
                    .onAppear {
                        logger.info("⏱ ContentView first-frame — main content visible")
                    }
            }
        }
        .onKeyPress(.tab, phases: .down) { keyPress in
            cyclePaneFocus(reverse: keyPress.modifiers.contains(.shift))
            return .handled
        }
        .onKeyPress(characters: CharacterSet(charactersIn: "\u{19}"), phases: .down) { _ in
            // Shift+Tab can arrive as back-tab (U+0019) rather than Tab+Shift.
            cyclePaneFocus(reverse: true)
            return .handled
        }
        // Option+Left/Right cycles between panes (sidebar → content → preview → inspector).
        // Plain left/right are reserved for inner-pane navigation (grid columns, DisclosureGroup expand).
        // Command+Left/Right navigates to previous/next sibling document (#593).
        .onKeyPress(.leftArrow, phases: .down) { keyPress in
            if keyPress.modifiers.contains(.command) {
                navigateSiblingPrevious()
                return .handled
            }
            if keyPress.modifiers.contains(.option) {
                cyclePaneFocus(reverse: true)
                return .handled
            }
            return .ignored
        }
        .onKeyPress(.rightArrow, phases: .down) { keyPress in
            if keyPress.modifiers.contains(.command) {
                navigateSiblingNext()
                return .handled
            }
            if keyPress.modifiers.contains(.option) {
                cyclePaneFocus(reverse: false)
                return .handled
            }
            return .ignored
        }
        .alert(item: $errorService.currentAlert) { errorModel in
            let message = errorModel.recoverySuggestion != nil ?
                "\(errorModel.message)\n\n\(errorModel.recoverySuggestion!)" :
                errorModel.message

            return Alert(
                title: Text(errorModel.title),
                message: Text(message),
                primaryButton: .default(Text("OK")) {
                    errorService.currentAlert = nil
                },
                secondaryButton: errorModel.isRecoverable ?
                    .default(Text("Retry")) {
                        // User requested retry - could trigger recovery action
                        errorService.currentAlert = nil
                    } : .cancel(Text("Dismiss")) {
                        errorService.currentAlert = nil
                    }
            )
        }
    }

    /// Main app content (when backend is connected)
    @ViewBuilder
    private var mainContentView: some View {
        let inspectorIsPresented = Binding(
            get: { effectiveShowInspectorSidebar },
            set: { showInspectorSidebar = $0 }
        )
        // Inspector is a NATIVE SwiftUI `.inspector()` column attached to the
        // NavigationSplitView, so it persists across all view modes (#1199) AND
        // the unified window toolbar/title spans it correctly — trailing toolbar
        // items sit above the inspector instead of the toolbar overrunning it
        // (#2033). It replaced the former window-level HStack sibling, which
        // macOS painted the toolbar across (the bug Daniel saw).
        //
        // The split-view column itself carries a very long chained-modifier
        // list (toolbar + ~16 .onChange/.onReceive handlers). To keep any single
        // `some View` expression inside the Swift type-checker's complexity
        // budget, that chain is broken across two intermediate properties:
        // `navigationSplitColumn` (NavigationSplitView + first half of modifiers)
        // and `decoratedNavigationSplitColumn` (the remaining modifiers).
        decoratedNavigationSplitColumn
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
            .popover(
                item: detailPopoverDocument,
                attachmentAnchor: .rect(.bounds),
                arrowEdge: .trailing
            ) { document in
                VStack(spacing: 0) {
                    HStack(spacing: 8) {
                        Image(systemName: "doc.text.magnifyingglass")
                            .foregroundStyle(.secondary)
                        Text(document.name)
                            .font(.headline)
                            .lineLimit(1)
                        Spacer(minLength: 0)
                        DetachInspectorButton(isEnabled: true) {
                            focusedDocument.select(document, libraryId: windowState.libraryId)
                            openWindow(id: "document-detail")
                        }
                    }
                    .padding(.horizontal, 12)
                    .frame(height: MiniToolbar<EmptyView, EmptyView>.standardHeight)

                    Divider()

                    DocumentInspector(document: document)
                }
                .frame(minWidth: 360, minHeight: 420)
            }

        // Listen for claim selection from inspector and sync to other panes
        .onReceive(NotificationCenter.default.publisher(for: .claimSelectedInInspector)) { notification in
            if let claimId = notification.userInfo?["claimId"] as? String {
                ClaimFocusState.shared.selectClaim(claimId: claimId)
            }
        }
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
            .focusedSceneValue(\.showDocumentGrid, $showDocumentGrid)
            .focusedSceneValue(\.showDocumentCanvas, $showDocumentCanvas)
            .focusedSceneValue(\.showReadingPane, $showReadingPane)
            .focusedSceneValue(
                \.navigationUndoAction,
                FocusedLibraryAction(isEnabled: navigationHistory.canGoBack, run: navigateBack)
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
        .navigationTitle(toolbarTitle)
        .modifier(NavigationSubtitleCompat(subtitle: breadcrumbSubtitle))
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
            #if canImport(AppKit)
            .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
                handleWillTerminate()
            }
            #endif
            .onReceive(NotificationCenter.default.publisher(for: .ficheroEntitySearchRequested)) { note in
                handleEntitySearchRequested(note)
            }
            .onReceive(NotificationCenter.default.publisher(for: .ficheroOpenClaimSource)) { note in
                handleOpenClaimSource(note)
            }
            .onChange(of: kgFocusState.sourceDocumentId) { _, _ in
                handleKGFocusChanged()
            }
            .onChange(of: kgFocusState.sourcePageLabel) { _, _ in
                handleKGFocusChanged()
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
                    selectedSidebarItemId: $selectedSidebarItemId,
                    browserSelection: $browserSelection,
                    detailDocument: $detailDocument,
                    columnVisibility: $columnVisibility,
                    editingWorkflow: $editingWorkflow,
                    isDropTargeted: $isDropTargeted,
                    isImporting: $isImporting,
                    importProgress: $importProgress,
                    importError: $importError,
                    handleDocumentChange: handleDocumentChange,
                    handleFileDrop: handleFileDrop
                )
            )
    }

    /// Detail-column toolbar content split out to keep the `NavigationSplitView`
    /// detail closure small enough for the Swift type-checker.
    @ToolbarContentBuilder
    private var detailToolbarContent: some ToolbarContent {
        contentPaneToolbarContent
        // Inspector toggle in the content section. .automatic on the detail
        // column view lands in the content-column toolbar section (#2309).
        trailingToolbarContent
        // Centred context label. .principal on the detail column centres
        // within the content section — visually near window centre at
        // typical sidebar widths (#2309).
        principalToolbarContent
    }

    @ViewBuilder
    private var inspectorContainerView: some View {
        if usesDockedInspector {
            #if os(visionOS)
            detailView
                // Inspector toggle in the INSPECTOR SECTION (far right).
                // Attaching to the inspector panel content (rather than the
                // detail column) places the button in the trailing inspector
                // section of the unified toolbar instead of the content
                // section. NavigationSplitView does not auto-remove column
                // toolbar contributions when a column is hidden, so the
                // toggle remains visible even when the inspector is closed
                // — same mechanism as the sidebar-section buttons (#2309).
                .toolbar {
                    if showInspectorToggle {
                        ToolbarItem(placement: .primaryAction) {
                            inspectorToggleButton
                        }
                    }
                }
            #else
            detailView
                // Inspector toggle in the INSPECTOR SECTION (far right).
                // Attaching to the inspector panel content (rather than the
                // detail column) places the button in the trailing inspector
                // section of the unified NSToolbar instead of the content
                // section. NavigationSplitView does not auto-remove column
                // toolbar contributions when a column is hidden, so the
                // toggle remains visible even when the inspector is closed
                // — same mechanism as the sidebar-section buttons (#2309).
                .toolbar {
                    if showInspectorToggle {
                        ToolbarItem(placement: .primaryAction) {
                            inspectorToggleButton
                        }
                    }
                }
                .inspectorColumnWidth(
                    min: CGFloat(ContentView.inspectorMinWidth),
                    ideal: 300,
                    max: CGFloat(ContentView.inspectorMaxWidth)
                )
            #endif
        } else {
            // Compact width (iPhone): the adaptive presenter routes the
            // inspector into the collapsed navigation stack, so it pushes from
            // the right and participates in back-swipe / back-button history.
            // This branch supplies ONLY the inspector content; the presenter
            // owns the stack-vs-docked choice outside this builder.
            detailView
        }
    }
}

// MARK: - Toolbar Content

extension ContentView {
    @ViewBuilder
    func toolbarToggleIcon(_ systemName: String, isActive: Bool) -> some View {
        Image(systemName: systemName)
            .symbolVariant(isActive ? .fill : .none)
            .padding(.horizontal, 5)
            .padding(.vertical, 3)
            .background(
                RoundedRectangle(cornerRadius: 5)
                    .fill(isActive ? Color.primary.opacity(0.1) : Color.clear)
            )
    }

    // MARK: Zoned toolbar (Mail-style)
    //
    // The window toolbar is organised into ACTION zones separated by flexible
    // spacers, modelled on Apple Mail (#2032). Presentation controls ("how it's
    // shown" — layout/view-mode pickers, library/canvas/reading pane toggles)
    // do NOT live here; they are in the View menu (ViewMenuCommands:
    // LibraryLayoutSection / PreviewModeSection / PaneVisibilitySection). The
    // main toolbar is verbs only.
    //
    // `mainToolbarContent` is a thin dispatcher to three bounded
    // `@ToolbarContentBuilder` sub-properties so no single builder grows large
    // enough to risk a type-check timeout.
    @ToolbarContentBuilder
    var mainToolbarContent: some ToolbarContent {
        // LEADING zone — back/forward history (content-column toolbar).
        leadingToolbarContent
    }

    /// LEADING zone: back/forward history navigation in the content-column toolbar.
    @ToolbarContentBuilder
    private var leadingToolbarContent: some ToolbarContent {
        ToolbarItemGroup(placement: .navigation) {
            Button {
                navigateBack()
            } label: {
                Label("Back", systemImage: "chevron.backward")
            }
            .help("Back (⌘')")
            .keyboardShortcut("'", modifiers: [.command])
            .disabled(!navigationHistory.canGoBack)

            Button {
                navigateForward()
            } label: {
                Label("Forward", systemImage: "chevron.forward")
            }
            .help("Forward (⌘⇧')")
            .keyboardShortcut("'", modifiers: [.command, .shift])
            .disabled(!navigationHistory.canGoForward)
        }
    }

    /// TRAILING zone: activity status (#2309).
    /// The inspector toggle moved to the `.inspector()` panel's toolbar so
    /// macOS places it in the inspector section (far right) rather than the
    /// content section (see `mainContentView`).
    @ToolbarContentBuilder
    private var trailingToolbarContent: some ToolbarContent {
        #if !os(macOS)
        if showInspectorToggle && !usesDockedInspector {
            ToolbarItem(placement: .topBarTrailing) {
                inspectorToggleButton
            }
        }
        #endif

        // Activity / error status — sits between the title and the inspector section.
        ToolbarItem(placement: .automatic) {
            HStack(spacing: 6) {
                if isImporting {
                    ProgressView()
                        .controlSize(.small)
                        .help(importProgress ?? "Importing…")
                }
                if importError != nil {
                    Image(systemName: "exclamationmark.circle.fill")
                        .foregroundStyle(.red)
                        .help(importError ?? "Import error")
                        .onTapGesture { importError = nil }
                }
            }
        }

        #if !os(macOS)
        ToolbarItem(placement: .primaryAction) {
            platformViewMenuButton
        }
        #endif
    }

    @ToolbarContentBuilder
    private var contentPaneToolbarContent: some ToolbarContent {
        if supportsReadingWorkspace {
            ToolbarItemGroup(placement: .automatic) {
                if showViewModePicker && availableViewDisplayModes.count > 1 {
                    viewDisplayModeMenu
                }

                Button {
                    setCanvasPaneVisible(!showDocumentCanvas)
                } label: {
                    Label("Preview Pane", systemImage: showDocumentCanvas ? "rectangle.center.inset.filled" : "rectangle")
                }
                .help(showDocumentCanvas ? "Hide preview pane" : "Show preview pane")

                Button {
                    setReadingPaneVisible(!showReadingPane)
                } label: {
                    Label("Reading Pane", systemImage: showReadingPane ? "text.book.closed.fill" : "text.book.closed")
                }
                .help(showReadingPane ? "Hide reading pane" : "Show reading pane")
            }
        }
    }

    private var viewDisplayModeMenu: some View {
        Menu {
            ForEach(availableViewDisplayModes) { mode in
                Button {
                    updateViewDisplayMode(mode)
                } label: {
                    Label(mode.label, systemImage: mode.icon)
                }
            }
        } label: {
            Label(viewDisplayMode.label, systemImage: viewDisplayMode.icon)
        }
        .help("Choose how library items are shown")
    }

    #if !os(macOS)
    @ViewBuilder
    private var platformViewMenuButton: some View {
        Menu {
            ViewMenuCommands()
                .environmentObject(viewSettings)
        } label: {
            Label("View", systemImage: "rectangle.split.3x1")
        }
        .help("Choose visible panes and document views")
    }
    #endif

    private var inspectorToggleButton: some View {
        Button {
            withAnimation(.easeInOut(duration: 0.2)) {
                showInspectorSidebar.toggle()
            }
        } label: {
            Label {
                Text("Inspector")
            } icon: {
                toolbarToggleIcon("sidebar.right", isActive: showInspectorSidebar)
            }
        }
        .help(showInspectorSidebar ? "Hide Inspector (⌘⌥I)" : "Show Inspector (⌘⌥I)")
    }

    /// PRINCIPAL zone: breadcrumb lozenge + scoped search (#2309/#2039).
    /// Layout: [Library Name] > [item icon + title] [search current content]
    /// The whole breadcrumb sits in a subtle rounded-rect lozenge with
    /// extra horizontal padding so it reads as a single interactive label.
    @ToolbarContentBuilder
    private var principalToolbarContent: some ToolbarContent {
        ToolbarItem(placement: .principal) {
            let libraryName: String? = {
                guard case .library(let doc) = viewMode, doc != nil else { return nil }
                return LibraryManager.shared.getLibrary(id: windowState.libraryId)?.displayName
            }()

            HStack(spacing: 4) {
                HStack(spacing: 4) {
                    if let libraryName {
                        HStack(spacing: 3) {
                            Image(systemName: "books.vertical")
                                .imageScale(.small)
                            Text(libraryName)
                                .font(.subheadline)
                        }
                        .foregroundStyle(.secondary)

                        Image(systemName: "chevron.right")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }

                    HStack(spacing: 3) {
                        Image(systemName: toolbarIcon)
                            .imageScale(.small)
                        Text(toolbarTitle)
                            .font(.headline)
                            .lineLimit(1)
                    }
                    .foregroundStyle(.primary)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(Color.primary.opacity(0.06))
                )

                TextField("Search \(toolbarTitle)", text: $toolbarSearchText)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 220)
                    .onSubmit {
                        runToolbarSearch(toolbarSearchText)
                    }
                    .help("Search current content")
            }
        }
    }

    private func syncFocusedDocumentSelection(_ document: Document?) {
        if let document {
            focusedDocument.select(document, libraryId: windowState.libraryId)
        } else {
            focusedDocument.clear()
        }
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

// MARK: - Preview
#Preview("Library Mode") {
    ContentView()
        .environmentObject(ViewSettings())
        .environmentObject(AppState())
        .frame(width: 1200, height: 700)
}
