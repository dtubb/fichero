import Combine
import OSLog
import SwiftUI
import UniformTypeIdentifiers

/// Structured logger for sidebar operations
let sidebarViewLogger = Logger(subsystem: "com.fichero.app", category: "Sidebar")

/// Universal Sidebar with Xcode-style mode switching
/// Mode bar at top, content changes based on selected mode
/// Each mode shows content grouped by library
struct SidebarView: View {
    @Binding var sidebarMode: SidebarMode
    @Binding var viewMode: AppViewMode
    @Binding var selectedItemId: String?

    // LibraryManager - shows all open libraries
    @ObservedObject var libraryManager: LibraryManager

    // Window state - needed to switch libraries when selecting items
    @EnvironmentObject var windowState: WindowState

    // API client for service calls
    @EnvironmentObject var apiClient: APIClient

    // Callback when documents are dropped to create a new chat
    var onCreateChatWithDocuments: (([String]) -> Void)?

    // Item type registry for extensible item creation (injected from ContentView)
    @ObservedObject var itemRegistry: ItemTypeRegistry

    // SidebarState for expansion persistence (internal for extension access)
    @StateObject var sidebarState: SidebarState

    // Rename and delete state (internal for extension access)
    @StateObject var renameState = RenameStateManager()
    @StateObject var deleteState = DeleteStateManager()

    // Cached sidebar items - rebuilt when service data changes (via Combine observers)
    @State var cachedLibraryHeaders: [SidebarItem] = []

    // Chain service for workflows sidebar (global - not per-library yet)
    @StateObject var chainService: ChainService

    // Chains loaded from ChainService
    @State var chains: [WorkflowChain] = []

    // Automation data (schedules and triggers)
    @State var schedules: [ScheduleInfo] = []
    @State var triggers: [TriggerInfo] = []
    @State var automationIsLoading = false

    // Batch data
    @State var batches: [BatchInfo] = []
    @State var batchesIsLoading = false

    // Activity data (historical runs)
    @State var historicalRunsByLibrary: [UUID: [ActivityItem]] = [:]
    @State var activityIsLoading = false

    // Store Combine subscriptions
    @State var cancellables = Set<AnyCancellable>()

    init(
        sidebarMode: Binding<SidebarMode>,
        viewMode: Binding<AppViewMode>,
        selectedItemId: Binding<String?>,
        libraryManager: LibraryManager,
        itemRegistry: ItemTypeRegistry,
        apiClient: APIClient,
        windowPersistenceId: String,
        onCreateChatWithDocuments: (([String]) -> Void)? = nil
    ) {
        self._sidebarMode = sidebarMode
        self._viewMode = viewMode
        self._selectedItemId = selectedItemId
        self.libraryManager = libraryManager
        self.itemRegistry = itemRegistry
        self.onCreateChatWithDocuments = onCreateChatWithDocuments
        self._sidebarState = StateObject(
            wrappedValue: SidebarState(windowId: windowPersistenceId)
        )
        // Initialize ChainService with apiClient
        self._chainService = StateObject(wrappedValue: ChainService(apiClient: apiClient))
    }

    var body: some View {
        sidebarContent
            .sidebarStyle()
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
            }
            .onChange(of: selectedItemId) { _, newId in
                // Handle selection changes
                sidebarViewLogger.info("selectedItemId changed to: \(newId ?? "nil")")
                if let id = newId {
                    let item = findItemById(id, in: allCachedItems)
                    handleSelection(item)
                }
            }
            .onChange(of: libraryManager.openLibraries.count) { _, _ in
                // Rebuild when libraries are added/removed
                rebuildCaches()

                // Resubscribe to service changes for new libraries
                setupServiceObservers()
            }
            .onChange(of: sidebarMode) { _, newMode in
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
                } else if newMode == .batches {
                    Task {
                        guard !Task.isCancelled else { return }
                        await loadBatchData()
                    }
                } else if newMode == .activity {
                    Task {
                        guard !Task.isCancelled else { return }
                        await loadActivityData()
                    }
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
            .sidebarFileImporter(
                isPresented: $sidebarState.showingFileImporter,
                importFiles: handleImportedFiles
            )
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
