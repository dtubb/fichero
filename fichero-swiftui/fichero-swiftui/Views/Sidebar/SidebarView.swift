import Combine
import OSLog
import SwiftUI
import UniformTypeIdentifiers

/// Structured logger for sidebar operations
let sidebarViewLogger = Logger(subsystem: "com.tubb.Fichero", category: "Sidebar")

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
    @Environment(WorkflowExecutionObserver.self) var executionObserver

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

    // Activity data (historical runs)
    @State var historicalRunsByLibrary: [UUID: [ActivityItem]] = [:]
    @State var activityIsLoading = false
    @State var selectedActivityItemIds: Set<String> = []
    @State var showingRenameLibraryPrompt = false
    @State var libraryToRenameId: UUID?
    @State var pendingLibraryName = ""

    // Store Combine subscriptions
    @State var cancellables = Set<AnyCancellable>()
    @State private var lastHandledSelectionId: String?

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

                guard !Task.isCancelled else { return }

                // Load historical activity runs for unified Activity section.
                if FeatureManager.shared.isActivityEnabled {
                    await loadActivityData()
                } else {
                    historicalRunsByLibrary = [:]
                }
            }
            .onChange(of: selectedItemId) { _, newId in
                // Handle selection changes
                sidebarViewLogger.info("selectedItemId changed to: \(newId ?? "nil")")
                if newId == nil || !(newId?.hasPrefix("run:") ?? false) {
                    selectedActivityItemIds.removeAll()
                } else if let runId = newId {
                    selectedActivityItemIds = [runId]
                }
                if let id = newId {
                    if lastHandledSelectionId == id {
                        return
                    }
                    lastHandledSelectionId = id
                    if id == "activity-browser" {
                        sidebarMode = .activity
                        viewMode = .activity(nil)
                        return
                    }
                    if id.hasPrefix("run:"),
                       let selectedRun = unifiedSelectedRun(forSidebarId: id) {
                        viewMode = .activity(selectedRun.toSelectedRun())
                        return
                    }
                    let item = findItemById(id, in: allCachedItems)
                    handleSelection(item)
                } else {
                    lastHandledSelectionId = nil
                }
            }
            .onChange(of: libraryManager.openLibraries.count) { _, _ in
                // Rebuild when libraries are added/removed
                rebuildCaches()

                // Resubscribe to service changes for new libraries
                setupServiceObservers()
            }
            .onChange(of: sidebarMode) { _, newMode in
                // Switching sections should allow re-selecting the same item in the
                // new section without onChange being blocked by lastHandledSelectionId
                // (which only guards against same-tick duplicate events, not cross-section
                // re-selection — #646).
                lastHandledSelectionId = nil
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
