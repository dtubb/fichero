import Combine
import OSLog
import SwiftUI
import UniformTypeIdentifiers

/// Structured logger for sidebar operations
let sidebarViewLogger = Logger(subsystem: "app.fichero.fichero", category: "Sidebar")

/// Universal Sidebar with Xcode-style mode switching
/// Mode bar at top, content changes based on selected mode
/// Each mode shows content grouped by library
struct SidebarView: View {
    /// The mode as a VALUE plus a setter, not a `Binding` (#5228): the host's mode is
    /// `@SceneStorage`, whose projected binding is a new identity on every render, so SwiftUI saw it
    /// as changed and re-ran this whole sidebar on every render of the window (~50-90 times in one
    /// launch). An unchanged value compares equal. Every `sidebarMode = x` below still works.
    let sidebarModeValue: SidebarMode
    let onSetSidebarMode: (SidebarMode) -> Void
    var sidebarMode: SidebarMode {
        get { sidebarModeValue }
        nonmutating set { onSetSidebarMode(newValue) }
    }
    @Binding var viewMode: AppViewMode
    @Bindable var selectionState: SidebarSelectionState

    // LibraryManager - shows all open libraries
    @Bindable var libraryManager: LibraryManager

    // Window state - needed to switch libraries when selecting items
    @Environment(AppState.self) var appState
    @Environment(WindowState.self) var windowState
    /// Double-click / trailing-affordance opens reuse the shared Finder-style
    /// new-window path (`WindowOpener`, #1685).
    @Environment(\.openWindow) var openWindow

    // API client for service calls
    @Environment(APIClient.self) var apiClient
    @Environment(WorkflowExecutionObserver.self) var executionObserver
    /// Saved agent workspaces (#3533) — optional so the sidebar is safe if the
    /// store isn't injected in a given host.

    var onOpenChatWithCurrentScope: (() -> Void)?

    /// Selecting a saved search runs it through the SAME transient toolbar
    /// search path as typing the query (#4106/S2) — the sidebar has no
    /// access to ContentView's toolbar field, so the host injects the hop.
    var onRunSavedSearch: ((SavedSearch) -> Void)?

    /// Keyboard focus handoff OUT of the sidebar (right-arrow on a leaf row) —
    /// mirrors LibraryView's onRequestPreviousPaneFocus path back in.
    var onRequestNextPaneFocus: (() -> Void)?

    // Item type registry for extensible item creation (injected from ContentView)
    @Bindable var itemRegistry: ItemTypeRegistry

    // SidebarState for expansion persistence (internal for extension access)
    @State var sidebarState: SidebarState

    // Rename and delete state (internal for extension access)
    @State var renameState = RenameStateManager()
    @State var deleteState = DeleteStateManager()

    // Cached sidebar items - rebuilt when service data changes (via Combine observers)
    @State var cachedLibraryHeaders: [SidebarItem] = []
    // #3862: last hash of ONLY the tree-shaping doc fields per library. Lets the
    // documentStore observer skip a whole-tree rebuild when a status poll mutated
    // currentDocuments/status but the sidebar structure is unchanged.
    @State var sidebarTreeSignatures: [UUID: Int] = [:]
    // #3862: header-derived, filtered item buckets cached per library so the body
    // stops re-filtering `header.children` on every sidebar state change.
    @State var cachedLibraryItemBuckets: [UUID: CachedLibraryItemBuckets] = [:]
    // Every cached row keyed by id, rebuilt with `cachedLibraryHeaders`. The
    // selection path used to answer "which item is this?" with a recursive walk
    // of the whole forest, ~4× per body pass — see `sidebarItemIndex`.
    @State var cachedItemIndex: [String: SidebarItem] = [:]
    /// When `cachedItemIndex` was last rebuilt (`sidebar.deselect-always-works`).
    @State var lastTreeRebuildAt: Date = .distantPast
    @State var sidebarFilterText = ""

    // Chain service for workflows sidebar (global - not per-library yet)
    @State var chainService: ChainService

    // Chains loaded from ChainService
    @State var chains: [WorkflowChain] = []

    // Automation data (schedules and triggers)
    @State var schedules: [ScheduleInfo] = []
    @State var triggers: [TriggerInfo] = []
    @State var automationIsLoading = false
    @State var automationLoadError: String?

    // Activity data (historical runs)
    @State var historicalRunsByLibrary: [UUID: [ActivityItem]] = [:]
    @State var activityIsLoading = false
    @State var activityLoadError: String?
    @State var showingRenameLibraryPrompt = false
    @State var libraryToRenameId: UUID?
    @State var pendingLibraryName = ""
    // Library the "Share Library…" header context-menu entry is presenting (#3149).
    @State var libraryToShare: LibraryManager.LibraryReference?
    // The always-there project whose document types the empty-area menu is editing
    // (`sidebar.top-section.empty-area-menu`; it has no header row to hold the sheet).
    @State var alwaysThereTypeEditorLibrary: LibraryManager.LibraryReference?

    /// The store-observer chains, held by reference so `setupServiceObservers()` can supersede
    /// the set a previous call armed (see `SidebarObserverChains`).
    @State var observerChains = SidebarObserverChains()
    // Internal (not private) so the extracted `handleSelectionChange` routing in
    // SidebarView+SelectionHandling.swift can read/update it (#2548).
    @State var lastHandledSelectionDestination: SidebarDestination?
    /// A selection from ANOTHER library, held until the window's library switch lands
    /// (#4995/#4996) — see `CrossLibraryRoute`.
    @State var pendingCrossLibraryRoute: CrossLibraryRoute.Pending?

    init(
        sidebarMode: SidebarMode,
        setSidebarMode: @escaping (SidebarMode) -> Void,
        viewMode: Binding<AppViewMode>,
        selectionState: SidebarSelectionState,
        libraryManager: LibraryManager,
        itemRegistry: ItemTypeRegistry,
        apiClient: APIClient,
        windowPersistenceId: String,
        onOpenChatWithCurrentScope: (() -> Void)? = nil,
        onRunSavedSearch: ((SavedSearch) -> Void)? = nil,
        onRequestNextPaneFocus: (() -> Void)? = nil
    ) {
        self.sidebarModeValue = sidebarMode
        self.onSetSidebarMode = setSidebarMode
        self._viewMode = viewMode
        self.selectionState = selectionState
        self.libraryManager = libraryManager
        self.itemRegistry = itemRegistry
        self.onOpenChatWithCurrentScope = onOpenChatWithCurrentScope
        self.onRunSavedSearch = onRunSavedSearch
        self.onRequestNextPaneFocus = onRequestNextPaneFocus
        self._sidebarState = State(
            wrappedValue: SidebarState(windowId: windowPersistenceId)
        )
        // Initialize ChainService with apiClient
        self._chainService = State(wrappedValue: ChainService(apiClient: apiClient))
    }

    var selectedItemId: String? {
        get { selectionState.selectedItemId }
        // nonmutating: mutates the @Bindable selectionState (class), not self.
        // Preserves the old @Binding semantics so non-mutating extension
        // methods (SidebarCreationHandlers) can still assign selectedItemId (#2548).
        nonmutating set { selectionState.selectedItemId = newValue }
    }

    var selectedDestination: SidebarDestination? {
        get { selectionState.selectedDestination }
        nonmutating set { selectionState.selectedDestination = newValue }
    }

    var body: some View {
        // Opt-in (FICHERO_PRINT_CHANGES=1): names the property that re-evaluated this body (#5228).
        if RenderDiagnostics.printChanges { Self._printChanges() }
        BodyCount.tick("SidebarView")
        return sidebarObserved
            .sidebarFocusedValues(config: SidebarFocusedValuesConfig(
                selectedItem: selectedItem,
                createFolder: handleCreateNewFolder,
                importFiles: importFiles,
                renameItem: handleRenameSelectedItem,
                deleteItem: handleDeleteSelection,
                createChat: createNewChat,
                createWorkflow: createNewWorkflow,
                createChain: createNewChain,
                createComparison: createNewComparison,
                createSchedule: createNewSchedule,
                createTrigger: createNewTrigger,
                openSelectionInNewTab: handleOpenSelectionInNewTab,
                openSelectionInNewWindow: handleOpenSelectionInNewWindow,
                deletableSelectionCount: sidebarDeleteTargets(
                    selectedItems, inheritedSelectionId: deleteState.inheritedSelectionId).count  // what Delete will take (#6235)
            ))
            .sidebarDeleteAlerts(
                deleteState: deleteState,
                performDelete: performDelete
            )
            .sidebarNewFolderDialog(
                sidebarState: sidebarState,
                createFolder: createFolder
            )
            .sidebarDropAlerts(sidebarState: sidebarState)
            .sidebarFileImporter(
                isPresented: $sidebarState.showingFileImporter,
                importFiles: handleImportedFiles
            )
            .alert("Rename Project", isPresented: $showingRenameLibraryPrompt) {
                TextField("Project Name", text: $pendingLibraryName)
                Button("Cancel", role: .cancel) { }
                Button("Rename") {
                    guard let libraryId = libraryToRenameId else { return }
                    libraryManager.renameLibrary(id: libraryId, to: pendingLibraryName)
                    rebuildCaches()
                }
            } message: {
                Text("Set a new display name for this project.")
            }
            // "Share Library…" (#3149) — same sheet the LibrarySharingBadge popover
            // presents, reached here from the library-header context menu.
            .sheet(item: $libraryToShare) { library in
                ShareLibrarySheet(library: library, usersStore: appState.usersStore)
            }
            // Share… on a FOLDER row (#5967): the same sheet, scoped to that folder.
            .sheet(item: $sidebarState.folderToShare) { target in
                if let library = libraryManager.getLibrary(id: target.libraryId) {
                    ShareLibrarySheet(library: library, usersStore: appState.usersStore, folder: target)
                }
            }
            // Edit Document Types… from the always-there project's empty-area menu: the same
            // sheet a project row's menu presents.
            .sheet(item: $alwaysThereTypeEditorLibrary) { library in
                PrototypeEditorSheet(entityService: library.entityService)
            }
    }
}

// NOTE: RenameStateManager, DeleteStateManager, and SidebarConstants
// are defined in separate files (SidebarStateManagers.swift, SidebarConstants.swift)
// Creation handlers are in SidebarCreationHandlers.swift
// Import/Delete/Rename actions are in SidebarActions.swift
// Service observers and data loading are in SidebarObservers.swift
// Helpers (allCachedItems, selectedItem, rebuildCaches, cachedItem) are in SidebarView+Helpers.swift
// View components (sidebarContent, modeContent) are in SidebarView+ViewComponents.swift
// Selection handling (handleSelection) is in SidebarView+SelectionHandling.swift
// Environment key (automationRefresh) is in SidebarView+Environment.swift
#Preview {
    @Previewable @State var sidebarMode: SidebarMode = .library
    @Previewable @State var viewMode: AppViewMode = .library(nil)

    let apiClient = APIClient()
    let selectionState = SidebarSelectionState()
    let itemRegistry = ItemTypeRegistry()

    NavigationStack {
        SidebarView(
            sidebarMode: sidebarMode,
            setSidebarMode: { sidebarMode = $0 },
            viewMode: $viewMode,
            selectionState: selectionState,
            libraryManager: LibraryManager.shared,
            itemRegistry: itemRegistry,
            apiClient: apiClient,
            windowPersistenceId: "preview"
        )
    }
    .environment(AppState())
    .environment(WindowState(libraryId: UUID()))
    .environment(apiClient)
    .environment(WorkflowExecutionObserver())
}
