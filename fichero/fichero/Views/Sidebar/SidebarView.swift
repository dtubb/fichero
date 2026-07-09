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
    @Binding var sidebarMode: SidebarMode
    @Binding var viewMode: AppViewMode
    @Bindable var selectionState: SidebarSelectionState

    // LibraryManager - shows all open libraries
    @Bindable var libraryManager: LibraryManager

    // Window state - needed to switch libraries when selecting items
    @Environment(AppState.self) var appState
    @Environment(WindowState.self) var windowState
    @Environment(\.undoManager) var undoManager

    // API client for service calls
    @Environment(APIClient.self) var apiClient
    @Environment(WorkflowExecutionObserver.self) var executionObserver

    var onOpenChatWithCurrentScope: (() -> Void)?

    // Item type registry for extensible item creation (injected from ContentView)
    @Bindable var itemRegistry: ItemTypeRegistry

    // SidebarState for expansion persistence (internal for extension access)
    @State var sidebarState: SidebarState

    // Rename and delete state (internal for extension access)
    @State var renameState = RenameStateManager()
    @State var deleteState = DeleteStateManager()

    // Cached sidebar items - rebuilt when service data changes (via Combine observers)
    @State var cachedLibraryHeaders: [SidebarItem] = []
    @State var sidebarFilterText = ""

    // Chain service for workflows sidebar (global - not per-library yet)
    @State var chainService: ChainService

    // Chains loaded from ChainService
    @State var chains: [WorkflowChain] = []

    // Automation data (schedules and triggers)
    @State var schedules: [ScheduleInfo] = []
    @State var triggers: [TriggerInfo] = []
    @State var automationIsLoading = false

    // Activity data (historical runs)
    @State var historicalRunsByLibrary: [UUID: [ActivityItem]] = [:]
    @State var activityIsLoading = false
    @State var selectedActivityItemIds: Set<String> = []
    @State var showingRenameLibraryPrompt = false
    @State var libraryToRenameId: UUID?
    @State var pendingLibraryName = ""
    // Library the "Share Library…" header context-menu entry is presenting (#3149).
    @State var libraryToShare: LibraryManager.LibraryReference?

    // Store Combine subscriptions
    @State var cancellables = Set<AnyCancellable>()
    // Internal (not private) so the extracted `handleSelectionChange` routing in
    // SidebarView+SelectionHandling.swift can read/update it (#2548).
    @State var lastHandledSelectionDestination: SidebarDestination?

    init(
        sidebarMode: Binding<SidebarMode>,
        viewMode: Binding<AppViewMode>,
        selectionState: SidebarSelectionState,
        libraryManager: LibraryManager,
        itemRegistry: ItemTypeRegistry,
        apiClient: APIClient,
        windowPersistenceId: String,
        onOpenChatWithCurrentScope: (() -> Void)? = nil
    ) {
        self._sidebarMode = sidebarMode
        self._viewMode = viewMode
        self.selectionState = selectionState
        self.libraryManager = libraryManager
        self.itemRegistry = itemRegistry
        self.onOpenChatWithCurrentScope = onOpenChatWithCurrentScope
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
        sidebarContent
            .sidebarStyle()
            // Suppress the NavigationSplitView sidebar-column title header (#2309).
            // The title is now shown centred in the main window toolbar by another
            // worker; the redundant sidebar column header is removed here.
            .navigationTitle("")
            .task {
                // Check cancellation before starting
                guard !Task.isCancelled else { return }

                // Build initial caches
                rebuildCaches()

                guard !Task.isCancelled else { return }

                // Subscribe to all library service changes
                setupServiceObservers()

                // Configure item registry handlers
                setupItemRegistry()

                guard !Task.isCancelled else { return }

                // Load chains for workflows sidebar
                if FeatureManager.shared.isWorkflowChainsEnabled {
                    await chainService.loadChains()
                } else {
                    chains = []
                }

                guard !Task.isCancelled else { return }

                // Load automation data (schedules and triggers)
                if FeatureManager.shared.isAutomationEnabled {
                    await loadAutomationData()
                } else {
                    schedules = []
                    triggers = []
                }

                guard !Task.isCancelled else { return }

                // Load historical activity runs for unified Activity section.
                if FeatureManager.shared.isActivityEnabled {
                    await loadActivityData()
                } else {
                    historicalRunsByLibrary = [:]
                }

                guard !Task.isCancelled else { return }

                // Drive a restored (@SceneStorage) selection into the view mode
                // now that caches exist — .onChange(of:) never fired for it
                // because the value didn't change on launch (#2548).
                reconcileRestoredSelection()
            }
            .onChange(of: selectionState.selectedDestination) { _, newDestination in
                // Route the live selection change to sidebarMode / viewMode.
                handleSelectionChange(newDestination)
            }
            .onChange(of: libraryManager.openLibraries.count) { _, _ in
                // Rebuild when libraries are added/removed
                rebuildCaches()

                // Resubscribe to service changes for new libraries
                setupServiceObservers()
            }
            .onChange(of: libraryManager.librariesLoadVersion) { _, _ in
                // Rebuild after any library finishes loading its data (#2472).
                // On iPhone, SidebarView.task fires before loadCollections()
                // completes; this is the stable signal that collections are ready.
                rebuildCaches()
                // A restored selection may only now resolve against the freshly
                // built caches — reconcile it into the view mode (#2548).
                reconcileRestoredSelection()
            }
            .onChange(of: sidebarMode) { _, newMode in
                // Switching sections should allow re-selecting the same item in the
                // new section without onChange being blocked by lastHandledSelectionId
                // (which only guards against same-tick duplicate events, not cross-section
                // re-selection — #646).
                lastHandledSelectionDestination = nil
                // Refresh data when switching to mode-specific sidebars
                // This ensures sidebar shows updated data after editor saves
                if newMode == .automation {
                    Task {
                        guard !Task.isCancelled else { return }
                        guard FeatureManager.shared.isAutomationEnabled else {
                            schedules = []
                            triggers = []
                            return
                        }
                        await loadAutomationData()
                    }
                } else if newMode == .activity {
                    Task {
                        guard !Task.isCancelled else { return }
                        await loadActivityData()
                    }
                }
            }
            .onChange(of: executionObserver.activeExecutions.count) { oldCount, newCount in
                guard FeatureManager.shared.isActivityEnabled else { return }
                // When a run starts or finishes, refresh historical runs so completed items persist.
                guard oldCount != newCount else { return }
                Task { @MainActor in
                    // Give backend activity writer a brief moment to persist completion events.
                    try? await Task.sleep(for: .milliseconds(400))
                    guard !Task.isCancelled else { return }
                    await loadActivityData()
                }
            }
            .onChange(of: libraryManager.globalLibrary?.activityStore.refreshToken ?? 0) { _, _ in
                guard FeatureManager.shared.isActivityEnabled else { return }
                guard case .activity = viewMode else { return }
                Task { @MainActor in
                    await loadActivityData()
                }
            }
            .sidebarFocusedValues(config: SidebarFocusedValuesConfig(
                selectedItem: selectedItem,
                createFolder: handleCreateNewFolder,
                importFiles: importFiles,
                renameItem: handleRenameSelectedItem,
                deleteItem: handleDeleteSelectedItem,
                createSearch: createNewSearch,
                createChat: createNewChat,
                createWorkflow: createNewWorkflow,
                createChain: createNewChain,
                createComparison: createNewComparison,
                createSchedule: createNewSchedule,
                createTrigger: createNewTrigger
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
            .alert("Rename Library", isPresented: $showingRenameLibraryPrompt) {
                TextField("Library Name", text: $pendingLibraryName)
                Button("Cancel", role: .cancel) { }
                Button("Rename") {
                    guard let libraryId = libraryToRenameId else { return }
                    libraryManager.renameLibrary(id: libraryId, to: pendingLibraryName)
                    rebuildCaches()
                }
            } message: {
                Text("Set a new display name for this library.")
            }
            // "Share Library…" (#3149) — same sheet the LibrarySharingBadge popover
            // presents, reached here from the library-header context menu.
            .sheet(item: $libraryToShare) { library in
                ShareLibrarySheet(library: library, usersStore: appState.usersStore)
            }
    }
}

// NOTE: RenameStateManager, DeleteStateManager, and SidebarConstants
// are defined in separate files (SidebarStateManagers.swift, SidebarConstants.swift)
// Creation handlers are in SidebarCreationHandlers.swift
// Import/Delete/Rename actions are in SidebarActions.swift
// Service observers and data loading are in SidebarObservers.swift
// Helpers (allCachedItems, selectedItem, rebuildCaches, findItemById) are in SidebarView+Helpers.swift
// View components (sidebarContent, modeContent) are in SidebarView+ViewComponents.swift
// Selection handling (handleSelection) is in SidebarView+SelectionHandling.swift
// Environment key (automationRefresh) is in SidebarView+Environment.swift
