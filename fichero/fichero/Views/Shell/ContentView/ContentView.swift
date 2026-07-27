import SwiftUI
import UniformTypeIdentifiers

/// Identifies which main pane has keyboard focus for Tab cycling
enum PaneFocus: Hashable {
    case sidebar, content, preview, reading, inspector
}

// Main content view with three-column navigation
// Switches between Library, Search, and Workflow views based on sidebar selection
//
// Architecture: This view has been refactored into multiple extensions for maintainability:
// - ContentView+State: Computed properties and state helpers
// - ContentView+SidebarLayout / +DetailLayout / +CompactReader / +Breadcrumb / +RootLayout:
//   View builders for sidebar, content, preview, inspector, and top-level composition
// - ContentView+Navigation: Content routing based on AppViewMode
// - ContentView+Actions: Action handlers and business logic
// - ContentView+Persistence: State serialization for @SceneStorage
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

    @Environment(ViewSettings.self) var viewSettings
    @Environment(AppState.self) var appState
    @Environment(APIClient.self) var apiClient
    @Environment(DocumentStore.self) var documentStore: DocumentStore
    @Environment(ConversationService.self) var conversationService
    @Environment(ImportService.self) var importService
    @Environment(WindowState.self) var windowState
    @Environment(WorkflowStore.self) var workflowStore
    @Environment(SavedSearchService.self) var savedSearchService
    @Environment(WorkflowStreamService.self) var workflowStreamService
    @Environment(WorkflowExecutionObserver.self) var executionObserver
    @Environment(KGFocusState.self) var kgFocusState
    @Environment(ArtifactService.self) var artifactService
    @Environment(EntityService.self) var entityService
    @Environment(KGCurationService.self) var kgCurationService
    @Environment(ArtifactStore.self) var artifactStore
    @Environment(EntityStore.self) var entityStore
    @Environment(ClaimStore.self) var claimStore
    @Environment(\.horizontalSizeClass) var horizontalSizeClass
    /// iOS has no `willTerminate`; backgrounding is the save signal (#3016).
    @Environment(\.scenePhase) var scenePhase
    @Environment(\.openWindow) var openWindow
    @Environment(ClaimFocusState.self) var claimFocusState
    @Environment(ResearchService.self) var researchService

    // MARK: - State (synced with @SceneStorage for persistence)

    // Runtime state - full objects for use in views
    @State var viewMode: AppViewMode = .library(nil)
    @State var detailDocument: Document?
    // Per-window instances (NOT `.shared`) so a search / source reveal in one
    // window never drives another (#3437). Injected into the subtree below.
    @State var entitySearchState = EntitySearchState()
    @State var claimSourceNavigationState = ClaimSourceNavigationState()
    /// Which Preview/Reader pane updates on the next library click (#3579).
    /// Per-window like the others; injected below, read by the pane views.
    @State var activeSurfaceState = ActiveSurfaceState()
    /// Drives the distraction-free full-window reading overlay (#2520).
    @State var isImmersiveReading = false
    /// Internal (not private): the toolbar's selection sync reads it from
    /// ContentView+Toolbar.swift, and `private` is file-scoped.
    @State var focusedDocument = FocusedDocument.shared
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
    @State var workflowReloadTask: Task<Void, Never>?

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
    @State var libraryToolbarState = LibraryToolbarState()

    // Map view persistence (latitude, longitude, zoom)
    @SceneStorage("mapLatitude") var mapLatitude: Double = 0.0
    @SceneStorage("mapLongitude") var mapLongitude: Double = 0.0
    @SceneStorage("mapZoom") var mapZoom: Double = 1.0
    @SceneStorage("sidebarWindowPersistenceId") var sidebarWindowPersistenceId: String = UUID().uuidString

    // Per-folder view mode persistence (JSON-encoded [folderId: displayMode.rawValue], per-window)
    @SceneStorage("folderViewDisplayModes") var folderViewDisplayModesJSON: String = "{}"

    @State var itemRegistry = ItemTypeRegistry()
    @State var performanceService = PerformanceService()
    @State var documentScrollSync = DocumentScrollSyncState()
    @State var toolbarSearchText: String = ""
    // Transient search (#4106/S2): a submitted toolbar query renders its
    // results INTO the Library view — no mode switch, no persisted object.
    // `nil` = normal folder browsing; non-nil = the library column shows
    // `searchResultDocuments` (relevance order) for this query.
    @State var activeSearchQuery: String?
    @State var searchResultDocuments: [Document] = []
    /// Page size for the active transient search; "Load More" grows it and
    /// re-runs the query (S9 UI half). Reset to the default on every new query.
    @State var transientSearchLimit: Int = ContentView.transientSearchPageSize
    /// Folder the user was browsing when the search ran (#4107/S3) — offered
    /// as a scope alongside the whole library in the results bar.
    @State var transientSearchContextFolder: TransientSearchFolder?
    /// Whether the active search is scoped to the context folder (true) or
    /// the whole library (false, the default).
    @State var transientSearchScopeIsFolder = false
    /// Real search parameters (#4112/S8), driven by the results-bar Options
    /// menu; saved searches apply their stored values. Sticky for the session.
    @State var transientSearchType = "hybrid"
    @State var transientSearchSortBy = "relevance"
    @State var transientSearchSortDirection = "desc"
    @State var navigationHistory = AppNavigationHistory()
    @State var isRestoringNavigationHistory = false

    // Injected from the window host (DocumentTabView) rather than grabbed as
    // `.shared` here, so ContentView's dependencies are swappable/testable —
    // prereq for the ContentView+State extractions (#3033). Still the shared
    // instances at runtime; injection is the seam.
    @Environment(ErrorService.self) var errorService
    @Environment(FeatureManager.self) var featureManager

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
        // #2960: ErrorService is @Observable via @Environment, which has no
        // projected binding — @Bindable gives `$errorService.currentAlert`.
        @Bindable var errorService = errorService
        return Group {
            // #4036/startup-transport-ux S1: NO full-window backend gate here.
            // `isCheckingBackend` / `!isBackendRunning` used to render a
            // full-window spinner / error screen, which held the real UI off
            // screen until the health check answered (~1s of a warm launch).
            // Engine phase — starting, connecting, every failure — is toolbar
            // chrome (`EngineStatusToolbarItem`), so real content mounts on
            // the first frame and data streams in when the engine answers.
            // Auth-gate ONLY once the backend has answered: pre-ready the
            // session phase is `.checking` (undetermined), and showing the
            // login wall then flashes it on every launch — loopback+bootstrap
            // is owner and must never see a login wall (#3941). A genuine
            // multiuser needs-login resolves right after the session refresh
            // and gates then.
            if appState.isBackendRunning,
                !appState.sessionStore.allowsLibraryAccess
                || appState.sessionStore.pendingInviteToken != nil {
                // Multi-user is on and there's no valid session yet — present the
                // login / first-run owner-setup screen instead of the library
                // (which would otherwise 401/403 against its own backend). (#2021)
                // A pending invite link (#3157) also routes here even when
                // already signed in, so the invitee can claim the new account.
                AuthGateView(session: appState.sessionStore)
            } else {
                mainContentView
                    .onAppear {
                        // The end of the launch timeline: real content on screen.
                        // `endLaunch` is idempotent — onAppear fires again on
                        // later re-appearances, which must not reopen or redraw
                        // the launch interval.
                        LaunchProfile.milestone("ContentView first-frame — main content visible")
                        LaunchProfile.endLaunch()
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
}

// MARK: - Preview
#Preview("Library Mode") {
    ContentView()
        .environment(ViewSettings())
        .environment(AppState())
        .environment(ErrorService.shared)
        .environment(FeatureManager.shared)
        .frame(width: 1200, height: 700)
}

// Size-class variants for the adaptive shell (#3019). The horizontalSizeClass
// environment override is what the routing policies read
// (shouldUseCompactNavigationFlow / CompactShellPolicy / shouldUseSplittablePane
// / InspectorPlacement.adaptiveDefault), so these render the two shells the
// ShellRoutingMatrixTests assert: regular = split + docked inspector, compact =
// stack navigation + sheet inspector.

#Preview("Shell — Regular (Mac/iPad)") {
    ContentView()
        .environment(ViewSettings())
        .environment(AppState())
        .environment(ErrorService.shared)
        .environment(FeatureManager.shared)
        .environment(\.horizontalSizeClass, .regular)
        .frame(width: 1200, height: 700)
}

#Preview("Shell — Compact (iPhone)") {
    ContentView()
        .environment(ViewSettings())
        .environment(AppState())
        .environment(ErrorService.shared)
        .environment(FeatureManager.shared)
        .environment(\.horizontalSizeClass, .compact)
        .frame(width: 390, height: 780)
}
