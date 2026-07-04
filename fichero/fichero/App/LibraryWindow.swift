// swiftlint:disable file_length
#if canImport(AppKit)
import AppKit
#endif
import FicheroAPIClient
import OSLog
import SwiftUI

#if os(macOS)

// MARK: - LibraryWindow

// swiftlint:disable type_body_length
/// Main window view - simplified to just track one library per window
struct LibraryWindow: View {
    @EnvironmentObject var libraryManager: LibraryManager
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var viewSettings: ViewSettings

    @StateObject private var windowState: WindowState

    // App-wide workflow execution observer (uses @Observable, not ObservableObject)
    @State private var executionObserver = WorkflowExecutionObserver()

    // Observed so the first-run sheet binding is reactive to completion.
    @ObservedObject private var featureManager = FeatureManager.shared

    @State private var hasInitialized = false
    @State private var showingFileImporter = false
    @State private var hostWindow: NSWindow?
    @SceneStorage("libraryWindow.libraryId") private var persistedLibraryId: String?

    // #2273 per-window state keys for duplicate-window restore and capture.
    // ContentView owns the live state; LibraryWindow just mirrors it.
    @SceneStorage("selectedSidebarItem") private var sceneSelectedItemId: String?
    @SceneStorage("viewModeType") private var sceneViewModeType: String = "library"
    @SceneStorage("viewModeItemId") private var sceneViewModeItemId: String?

    @Environment(\.openWindow) private var openWindow

    /// Seed handed to a window opened via `openWindow(value: WindowSeed)`
    /// (Duplicate Window, #2262). `nil` for the primary / File ▸ New Window
    /// path, which keeps its existing pending-library + restore behavior.
    private let seed: WindowSeed?

    let libraryWindowLogger = Logger(subsystem: "app.fichero.fichero", category: "LibraryWindow")

    init(seed: WindowSeed? = nil) {
        self.seed = seed
        _windowState = StateObject(wrappedValue: WindowState(libraryId: UUID()))
    }

    // Extracted from `body` so the ~40-modifier per-library environment chain
    // type-checks as its own expression — keeping it inline with the window's
    // sheet/onChange/focusedSceneValue chain overran the Swift type-checker's
    // budget once the #2262 Duplicate-Window plumbing was added.
    @ViewBuilder
    private var libraryWindowContent: some View {
        Group {
            if let library = windowState.library {
                LibraryWorkspaceRoot(
                    library: library,
                    windowState: windowState,
                    executionObserver: executionObserver
                )
            } else {
                // No library open yet — returning users see a simple create/open prompt.
                // First-run users are handled by the FirstRunWindow sheet below.
                noLibraryView
            }
        }
    }

    // Window chrome (accessor, file importer, scene-value command wiring, titles)
    // split out so neither this nor the sheet chain below overruns the type-checker.
    private var libraryWindowChrome: some View {
        libraryWindowContent
        .background(WindowAccessor { window in
            hostWindow = window
            syncHostWindowMetadata()
        })
        .fileImporter(
            isPresented: $showingFileImporter,
            allowedContentTypes: [.package],
            allowsMultipleSelection: false
        ) { result in
            handleFileImport(result)
        }
        // Scene-scoped so the File-menu commands resolve whenever this window
        // is key — not only while a descendant view holds keyboard focus.
        // Plain `.focusedValue` left ⌘N / "New Library…" disabled until some
        // inner control happened to be focused (#2042). Matches the rest of the
        // app's menu plumbing (sidebarMode, showInspector, librarySelectAll…).
        .focusedSceneValue(\.openLibraryAction, FocusedLibraryAction(isEnabled: true, run: { showingFileImporter = true }))
        .focusedSceneValue(\.newWindowAction, FocusedLibraryAction(isEnabled: true, run: { handleNewWindow() }))
        .focusedSceneValue(\.duplicateWindowAction, duplicateWindowAction)
        .focusedSceneValue(\.newLibraryAction, FocusedLibraryAction(isEnabled: true, run: { handleNewLibrary() }))
        .focusedSceneValue(\.saveLibraryAction, FocusedLibraryAction(isEnabled: true, run: { handleSaveLibrary() }))
        .focusedSceneValue(\.closeLibraryAction, closeLibraryAction)
        // Keep titlebar chrome minimal; ContentView manages in-window context.
        .navigationTitle("")
        .navigationSubtitle("")
    }

    // App-level sheet presenters, split out from the onChange chain in `body`.
    private var libraryWindowSheets: some View {
        libraryWindowChrome
        // App-level sheets must be here to work when no library is open.
        // AI providers/models now live inside the native Settings window (#2586).
        .sheet(isPresented: Binding(
            get: { appState.showAddProvider },
            set: { appState.showAddProvider = $0 }
        )) {
            AddProviderSheet(
                onAdd: {
                    await appState.loadProviders()
                    appState.isFirstLaunchProviderSetup = false
                },
                isFirstLaunch: appState.isFirstLaunchProviderSetup
            )
            .environmentObject(appState.providerService)
        }
        .sheet(isPresented: Binding(
            get: { appState.showMCPServers },
            set: { appState.showMCPServers = $0 }
        )) {
            MCPServersSheet()
                .environmentObject(appState)
                .environmentObject(appState.mcpService)
        }
        // Notes now live per-document in the inspector's Notes tab
        // (DocumentNotesTab, #1500) — the standalone browser sheet is retired.
        // Integrations sheets
        .sheet(isPresented: Binding(
            get: { appState.showFolderWatchers },
            set: { appState.showFolderWatchers = $0 }
        )) {
            IntegrationsPlaceholderSheet(
                title: "Folder Watchers",
                description: "Automatically process files when added to watched folders.",
                icon: "folder.badge.gearshape"
            )
        }
        .sheet(isPresented: Binding(
            get: { appState.showAppObservers },
            set: { appState.showAppObservers = $0 }
        )) {
            IntegrationsPlaceholderSheet(
                title: "App Observers",
                description: "Trigger workflows based on app events (e.g., when files are saved in specific apps).",
                icon: "app.badge"
            )
        }
        .sheet(isPresented: Binding(
            get: { appState.showAutomationRules },
            set: { appState.showAutomationRules = $0 }
        )) {
            IntegrationsPlaceholderSheet(
                title: "Automation Rules",
                description: "Create rules to automatically organize and process documents.",
                icon: "gearshape.2"
            )
        }
        // First-run onboarding (#1947 — sole first-run path, replaces ContentView sheet).
        // It opens once the backend is reachable and stays up until Finish, even if a
        // library is assigned while the user moves through the onboarding steps.
        .sheet(isPresented: Binding(
            get: { appState.isBackendRunning && !featureManager.firstRunCompleted },
            set: { if !$0 { featureManager.firstRunCompleted = true } }
        )) {
            FirstRunWindow()
                .environmentObject(appState)
        }
    }

    var body: some View {
        libraryWindowSheets
        // React to currentLibraryId changes (from Finder open, etc.)
        // Safari model: switch current window to the new library
        .onChange(of: libraryManager.currentLibraryId) { _, newId in
            guard let id = newId,
                  libraryManager.getLibrary(id: id) != nil else { return }

            // Switch this window to the new library. Route through assignLibrary
            // so the scene's @SceneStorage("libraryWindow.libraryId") stays in
            // sync — otherwise a window that switched library via Finder open /
            // Open Recent would restore the STALE library on relaunch (#2273).
            guard windowState.libraryId != id else { return }
            assignLibrary(id: id)
            libraryWindowLogger.info("Switched to library: \(id)")
        }
        .onChange(of: windowState.libraryId) { _, _ in
            syncHostWindowMetadata()
        }
        .onChange(of: windowState.library?.url) { _, _ in
            syncHostWindowMetadata()
        }
        .onAppear {
            guard !hasInitialized else { return }
            hasInitialized = true
            initializeWindow()
            syncHostWindowMetadata()
        }
    }

    // MARK: - Initialization

    private func initializeWindow() {
        libraryWindowLogger.info("""
            initializeWindow - openLibraries=\(libraryManager.openLibraries.count), \
            currentLibraryId=\(libraryManager.currentLibraryId?.uuidString ?? "nil")
            """)

        // Priority 0: a WindowSeed (Duplicate Window, #2262) clones an existing
        // window's library + selection + active lens. Write the #2273
        // scene-storage keys BEFORE the library mounts so ContentView restores
        // into the cloned state, then assign the seeded library via the shared
        // assignLibrary path (which also persists it for next launch).
        if let seed, let resolvedId = resolveSeedLibrary(seed) {
            sceneSelectedItemId = seed.selectedItemId
            sceneViewModeType = seed.viewModeType ?? "library"
            sceneViewModeItemId = seed.viewModeItemId
            assignLibrary(id: resolvedId)
            libraryWindowLogger.info("Seeded duplicated window from library: \(resolvedId)")
            return
        }

        if let pendingId = libraryManager.pendingWindowLibraryIds.first,
           libraryManager.getLibrary(id: pendingId) != nil {
            libraryWindowLogger.info("Consuming pendingWindowLibraryId: \(pendingId)")
            libraryManager.pendingWindowLibraryIds.removeFirst()
            assignLibrary(id: pendingId)
            return
        }

        // Priority 0: Restore the library this scene was showing last time.
        if let persistedLibraryId,
           let restoredId = UUID(uuidString: persistedLibraryId),
           libraryManager.getLibrary(id: restoredId) != nil {
            libraryWindowLogger.info("Restoring persisted libraryId: \(restoredId)")
            assignLibrary(id: restoredId)
            return
        }

        // Priority 1: Use currentLibraryId (set by handleOpenURL or restoreSavedLibraries)
        if let currentId = libraryManager.currentLibraryId,
           libraryManager.getLibrary(id: currentId) != nil {
            libraryWindowLogger.info("Using currentLibraryId: \(currentId)")
            assignLibrary(id: currentId)
            return
        }

        // Priority 2: Use first open library if any exist (restored on app launch)
        if let first = libraryManager.openLibraries.first {
            libraryWindowLogger.info("Using first library: \(first.displayName)")
            assignLibrary(id: first.id)
            return
        }

        // Priority 3: No library - show welcome screen
        libraryWindowLogger.info("No library available - showing welcome screen")
    }

    private func assignLibrary(id: UUID) {
        windowState.libraryId = id
        persistedLibraryId = id.uuidString
        libraryWindowLogger.info("Assigned library: \(id)")
    }

    private func createNewLibrary() {
        let library = libraryManager.createNewLibrary()
        assignLibrary(id: library.id)
        libraryWindowLogger.info("Created and assigned new library: \(library.displayName)")
    }

    // MARK: - Actions

    private func handleFileImport(_ result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            guard let url = urls.first else { return }
            let library = libraryManager.openLibrary(at: url)
            assignLibrary(id: library.id)
            libraryWindowLogger.info("Opened library: \(library.displayName)")
        case .failure(let error):
            libraryWindowLogger.error("Failed to open library: \(error.localizedDescription)")
        }
    }

    private func handleNewWindow() {
        libraryManager.currentLibraryId = windowState.libraryId
        openWindow(id: "main")
    }

    /// Resolve the library a WindowSeed refers to: prefer the already-open
    /// library by id (the Duplicate Window case — same process, same library),
    /// falling back to re-opening it from its on-disk path if a restored seed
    /// outlived the source library being closed.
    private func resolveSeedLibrary(_ seed: WindowSeed) -> UUID? {
        if let id = UUID(uuidString: seed.libraryId),
           libraryManager.getLibrary(id: id) != nil {
            return id
        }
        if let path = seed.libraryPath {
            return libraryManager.openLibrary(at: URL(fileURLWithPath: path), makeCurrent: false).id
        }
        return nil
    }

    /// Duplicate Window (#2262): clone THIS window's library + selection + lens
    /// into a brand-new window. Reads the live #2273 scene-storage state and
    /// hands it to the value-seeded `WindowGroup(for: WindowSeed.self)` via
    /// `openWindow(value:)`. `nil` when no library is open (menu item disabled).
    private var duplicateWindowAction: FocusedLibraryAction? {
        guard windowState.library != nil else { return nil }
        return FocusedLibraryAction(isEnabled: true, run: { handleDuplicateWindow() })
    }

    private func handleDuplicateWindow() {
        guard let library = windowState.library else { return }
        let seed = WindowSeed(
            libraryId: library.id.uuidString,
            libraryPath: libraryManager.isTemporaryLibrary(library.url) ? nil : library.url.path,
            selectedItemId: sceneSelectedItemId,
            viewModeType: sceneViewModeType,
            viewModeItemId: sceneViewModeItemId
        )
        openWindow(value: seed)
        libraryWindowLogger.info("Duplicated window for library: \(library.id)")
    }

    private func handleNewLibrary() {
        let savePanel = NSSavePanel()
        savePanel.allowedContentTypes = [.package]
        savePanel.canCreateDirectories = true
        savePanel.nameFieldStringValue = "Untitled.fichero"
        savePanel.title = "Create New Database"
        savePanel.message = "Choose where to save your new database."
        savePanel.prompt = "Create"

        if savePanel.runModal() == .OK, let url = savePanel.url {
            let withExtension = url.pathExtension.lowercased() == "fichero"
                ? url
                : url.appendingPathExtension("fichero")
            // NFC-normalize the new package's name so we never create a
            // mojibake-variant path on disk (#3076); the user-chosen parent dir
            // (already on disk) is left untouched.
            let finalURL = withExtension.nfcNormalizedLastComponent

            // Create unsaved library, immediately save to chosen location, then
            // open it in a NEW window (New Library… is distinct from New Window,
            // which reuses the current library). Reuses the same pending-library
            // → openWindow("main") affordance as every other open-in-new-window
            // path (WindowOpener), so the fresh scene picks the library up on init.
            let newLibrary = libraryManager.createNewLibrary()
            do {
                try libraryManager.saveLibrary(newLibrary.id, to: finalURL)
                WindowOpener.open(libraryId: newLibrary.id, asTab: false, using: openWindow)
                libraryWindowLogger.info("Created and saved new library: \(finalURL.lastPathComponent)")
            } catch {
                libraryWindowLogger.error("Failed to create new library: \(error.localizedDescription)")
            }
        }
    }

    private func handleSaveLibrary() {
        guard let library = windowState.library else { return }

        let savePanel = NSSavePanel()
        savePanel.allowedContentTypes = [.package]
        savePanel.canCreateDirectories = true
        savePanel.nameFieldStringValue = library.displayName + ".fichero"
        savePanel.message = "Choose a location to save your library"

        savePanel.begin { response in
            guard response == .OK, let url = savePanel.url else { return }

            // NFC-normalize the package name before saving (#3076) so a name
            // like "Chocó" is never written as an NFD-variant path.
            let finalURL = url.nfcNormalizedLastComponent
            do {
                try libraryManager.saveLibrary(windowState.libraryId, to: finalURL)
                libraryWindowLogger.info("Saved library to: \(finalURL.path)")
            } catch {
                libraryWindowLogger.error("Failed to save: \(error.localizedDescription)")
            }
        }
    }

    private var closeLibraryAction: FocusedLibraryAction? {
        guard let library = windowState.library,
              library.id != LibraryManager.globalLibraryId else {
            return nil
        }

        return FocusedLibraryAction(isEnabled: true, run: {
            closeLibraryFromCurrentWindow(library)
        })
    }

    private func closeLibraryFromCurrentWindow(_ library: LibraryManager.LibraryReference) {
        let wasCurrent = windowState.libraryId == library.id
        libraryManager.closeAndUnregisterLibrary(library.id)
        if wasCurrent {
            windowState.libraryId = LibraryManager.globalLibraryId
            persistedLibraryId = LibraryManager.globalLibraryId.uuidString
        }
    }

    private func syncHostWindowMetadata() {
        hostWindow?.representedURL = windowState.library?.url
    }
}
// swiftlint:enable type_body_length

// MARK: - Empty state (no library open, first-run already completed)

private extension LibraryWindow {
    /// Returning-user empty state: shown when no library is open and the
    /// first-run wizard has already been completed.  First-time users see
    /// the FirstRunWindow sheet instead (which handles library creation).
    var noLibraryView: some View {
        VStack(spacing: 24) {
            Image(systemName: "doc.richtext")
                .font(.largeTitle.weight(.semibold))
                .foregroundColor(.accentColor)

            Text("Fichero")
                .font(.largeTitle)
                .fontWeight(.semibold)

            Text("Create a new library or open an existing one to get started.")
                .font(.body)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            HStack(spacing: 16) {
                LibrarySetupActionsRow(
                    primaryTitle: "New Library",
                    primaryIcon: "plus",
                    primaryAction: createNewLibrary,
                    selectedLabel: nil
                )
                .buttonStyle(.borderedProminent)

                Button { showingFileImporter = true } label: {
                    Label("Open Library", systemImage: "folder")
                }
                .buttonStyle(.bordered)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(40)
    }
}

private struct WindowAccessor: NSViewRepresentable {
    let onResolve: (NSWindow?) -> Void

    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.async {
            onResolve(view.window)
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        DispatchQueue.main.async {
            onResolve(nsView.window)
        }
    }
}

#endif
