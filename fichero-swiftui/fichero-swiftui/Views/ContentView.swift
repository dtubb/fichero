import SwiftUI
import UniformTypeIdentifiers
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ContentView")

/// Identifies which main pane has keyboard focus for Tab cycling
enum PaneFocus: Hashable {
    case sidebar, content, inspector
}

/// Main content view with three-column navigation
/// Switches between Library, Search, and Workflow views based on sidebar selection
///
/// Architecture: This view has been refactored into multiple extensions for maintainability:
/// - ContentView+State: Computed properties and state helpers
/// - ContentView+ViewBuilders: View builders for sidebar, content, preview, inspector
/// - ContentView+Navigation: Content routing based on AppViewMode
/// - ContentView+Actions: Action handlers and business logic
/// - ContentView+Persistence: State serialization for @SceneStorage
struct ContentView: View {
    // MARK: - Environment

    @EnvironmentObject var viewSettings: ViewSettings
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var apiClient: APIClient
    @EnvironmentObject var documentStore: DocumentStore
    @EnvironmentObject var conversationService: ConversationServiceGenerated
    @EnvironmentObject var importService: ImportServiceGenerated
    @EnvironmentObject var windowState: WindowState
    @EnvironmentObject var workflowStore: WorkflowStore
    @EnvironmentObject var savedSearchService: SavedSearchServiceGenerated

    // MARK: - State (synced with @SceneStorage for persistence)

    // Runtime state - full objects for use in views
    @State var viewMode: AppViewMode = .library(nil)
    @State var detailDocument: Document?
    @State var columnVisibility: NavigationSplitViewVisibility = .all
    @State var browserSelection: Set<String> = []

    // Persisted state (@SceneStorage) - synced via .onAppear and .onChange
    @SceneStorage("selectedSidebarItem") var selectedSidebarItemId: String?
    @SceneStorage("columnVisibilityRaw") var columnVisibilityRaw: Int = 2 // 2 = .all
    @SceneStorage("browserSelectionData") var browserSelectionData: Data = Data()
    @SceneStorage("viewModeType") var storedViewModeType: String = "library"
    @SceneStorage("viewModeItemId") var storedViewModeItemId: String?

    // Workflow state
    @State var editingWorkflow: Workflow = Workflow(name: "New Workflow", description: "")

    // Chat state (shared between ChatView and ChatInspectorView)
    @State var chatSelectedDocuments: Set<String> = []

    // Main toolbar state (per-window persistence)
    @SceneStorage("viewDisplayMode") var viewDisplayMode: ViewDisplayMode = .icon
    @SceneStorage("currentLayoutMode") var currentLayoutMode: LayoutMode = .standard
    @SceneStorage("sidebarMode") var sidebarMode: SidebarMode = .library

    // Column visibility persistence
    @SceneStorage("sidebarWidth") var sidebarWidth: Double = 280
    @SceneStorage("contentWidth") var contentWidth: Double = 600
    @SceneStorage("inspectorWidth") var inspectorWidth: Double = 250
    @SceneStorage("showSidebar") var showSidebar: Bool = true
    @SceneStorage("showInspectorSidebar") var showInspectorSidebar: Bool = true

    // Map view persistence (latitude, longitude, zoom)
    @SceneStorage("mapLatitude") var mapLatitude: Double = 0.0
    @SceneStorage("mapLongitude") var mapLongitude: Double = 0.0
    @SceneStorage("mapZoom") var mapZoom: Double = 1.0

    // Per-folder view mode persistence (JSON-encoded [folderId: displayMode.rawValue])
    @AppStorage("folderViewDisplayModes") var folderViewDisplayModesJSON: String = "{}"

    @StateObject var itemRegistry = ItemTypeRegistry()
    @StateObject var performanceService = PerformanceService()

    // Error service (using singleton pattern)
    @ObservedObject var errorService = ErrorService.shared

    // Pane focus state for Tab cycling
    @FocusState var focusedPane: PaneFocus?

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

                    Divider()
                        .frame(width: 200)

                    VStack(alignment: .leading, spacing: 8) {
                        Text("To start the API, run:")
                            .font(.headline)

                        Text("cd /Users/dtubb/code/fichero_main/fichero")
                            .font(.system(.body, design: .monospaced))
                            .padding(8)
                            .background(Color(nsColor: .controlBackgroundColor))
                            .cornerRadius(4)

                        Text("PYTHONPATH=src .venv/bin/uvicorn fichero.api.main:app --port 8765")
                            .font(.system(.body, design: .monospaced))
                            .padding(8)
                            .background(Color(nsColor: .controlBackgroundColor))
                            .cornerRadius(4)
                    }

                    HStack(spacing: 16) {
                        Button("Retry") {
                            Task { @MainActor in
                                await appState.checkBackendHealth()
                            }
                        }
                        .keyboardShortcut("r", modifiers: [.command])

                        Button("Quit") {
                            NSApplication.shared.terminate(nil)
                        }
                        .keyboardShortcut("q", modifiers: [.command])
                    }
                    .padding(.top, 10)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                mainContentView
                    .onKeyPress(.tab, phases: .down) { keyPress in
                        cyclePaneFocus(reverse: keyPress.modifiers.contains(.shift))
                        return .handled
                    }
            }
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
        NavigationSplitView(columnVisibility: $columnVisibility) {
            sidebarContent
        } content: {
            centerContent
        } detail: {
            detailView
        }
        .navigationSplitViewStyle(.prominentDetail)
        .navigationTitle(toolbarTitle)
        .navigationSubtitle("")
        .toolbar(removing: .sidebarToggle)
        .onAppear {
            // Restore all persisted state from @SceneStorage
            restorePersistedState()
            // Initialize column visibility based on persisted inspector state
            updateColumnVisibility()
        }
        .onChange(of: showInspectorSidebar) { _, _ in
            // Update column visibility when inspector toggle changes
            updateColumnVisibility()
        }
        .toolbar {
            // Left side: Layout picker, View mode picker, Plus button
            // Conditional based on sidebar mode
            if showNavigationToolbar {
                ToolbarItemGroup(placement: .navigation) {
                    // Layout mode picker (None/Standard/Widescreen) - only for modes with preview
                    if showLayoutPicker {
                        Picker("Layout", selection: $currentLayoutMode) {
                            ForEach(LayoutMode.allCases) { mode in
                                Label(mode.rawValue, systemImage: mode.icon)
                                    .labelStyle(.iconOnly)
                                    .tag(mode)
                            }
                        }
                        .pickerStyle(.segmented)
                        .help("Layout: \(currentLayoutMode.rawValue)")
                        .onChange(of: currentLayoutMode) { _, newMode in
                            withAnimation {
                                // Sync toolbar with View menu previewMode
                                viewSettings.previewMode = switch newMode {
                                case .none: .none
                                case .standard: .standard
                                case .widescreen: .widescreen
                                }
                            }
                        }
                    }

                    // View mode picker (Icon/List/Table/Map) - only for Library/Search
                    if showViewModePicker {
                        Picker("View", selection: $viewDisplayMode) {
                            ForEach(ViewDisplayMode.allCases) { mode in
                                Label(mode.rawValue, systemImage: mode.icon)
                                    .labelStyle(.iconOnly)
                                    .tag(mode)
                            }
                        }
                        .pickerStyle(.segmented)
                        .help("View as: \(viewDisplayMode.rawValue)")
                        .onChange(of: viewDisplayMode) { _, newMode in
                            // Sync toolbar with View menu libraryLayout
                            viewSettings.libraryLayout = switch newMode {
                            case .icon: .icons
                            case .list: .list
                            case .table: .table
                            case .map: .map
                            }
                            // Save per-folder display mode
                            saveDisplayMode(newMode, for: selectedSidebarItemId)
                        }
                    }

                    // Add menu (Plus button)
                    AddItemMenu(registry: itemRegistry, style: .button)
                        .help("Add new item (⌘N)")
                }
            }

            // Far right: Inspector toggle (after search widget, explicit trailing position)
            // Only show for content modes that use inspector
            if showInspectorToggle {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        withAnimation {
                            showInspectorSidebar.toggle()
                        }
                    } label: {
                        Image(systemName: "sidebar.right")
                    }
                    .help(showInspectorSidebar ? "Hide Inspector (⌘⌥I)" : "Show Inspector (⌘⌥I)")
                }
            }
        }
        .onChange(of: viewSettings.previewMode) { _, newPreviewMode in
            // Sync View menu changes back to toolbar layout picker
            let newLayoutMode = switch newPreviewMode {
            case .none: LayoutMode.none
            case .standard: LayoutMode.standard
            case .widescreen: LayoutMode.widescreen
            }

            if currentLayoutMode != newLayoutMode {
                withAnimation {
                    currentLayoutMode = newLayoutMode
                }
            }
        }
        .onChange(of: viewSettings.libraryLayout) { _, newLibraryLayout in
            // Sync View menu changes back to toolbar view mode picker
            let newDisplayMode = switch newLibraryLayout {
            case .icons: ViewDisplayMode.icon
            case .list: ViewDisplayMode.list
            case .table: ViewDisplayMode.table
            case .map: ViewDisplayMode.map
            }

            if viewDisplayMode != newDisplayMode {
                viewDisplayMode = newDisplayMode
            }
        }
        .onChange(of: viewMode) { oldMode, newMode in
            // Auto-save workflow when navigating away from a workflow
            if case .workflow(let oldWorkflow) = oldMode, let workflow = oldWorkflow {
                // Capture the editing workflow content before it changes
                let workflowToSave = editingWorkflow
                Task { @MainActor in
                    await autoSaveWorkflow(workflowId: workflow.id, workflow: workflowToSave)
                }
            }

            // Persist view mode to @SceneStorage
            let (type, id) = serializeViewMode(newMode)
            storedViewModeType = type
            storedViewModeItemId = id
        }
        .onChange(of: selectedSidebarItemId) { _, newFolderId in
            // Restore per-folder view mode when switching folders
            if let saved = displayMode(for: newFolderId) {
                viewDisplayMode = saved
            }
        }
        .onChange(of: columnVisibility) { _, newVisibility in
            // Persist column visibility to @SceneStorage
            // Map NavigationSplitViewVisibility to raw int for @SceneStorage
            if newVisibility == .automatic {
                columnVisibilityRaw = 0
            } else if newVisibility == .detailOnly {
                columnVisibilityRaw = 1
            } else if newVisibility == .all {
                columnVisibilityRaw = 2
            } else if newVisibility == .doubleColumn {
                columnVisibilityRaw = 3
            } else {
                columnVisibilityRaw = 0
            }
        }
        .onChange(of: browserSelection) { _, newSelection in
            // Persist browser selection to @SceneStorage
            if let encoded = try? JSONEncoder().encode(newSelection) {
                browserSelectionData = encoded
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
            // Auto-save workflow when app quits
            if case .workflow(let workflow) = viewMode, let workflowItem = workflow {
                let workflowToSave = editingWorkflow
                Task { @MainActor in
                    await autoSaveWorkflow(workflowId: workflowItem.id, workflow: workflowToSave)
                }
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
}

// MARK: - Preview

#Preview("Library Mode") {
    ContentView()
        .environmentObject(ViewSettings())
        .environmentObject(AppState())
        .frame(width: 1200, height: 700)
}
