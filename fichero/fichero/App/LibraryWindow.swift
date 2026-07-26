#if canImport(AppKit)
import AppKit
#endif
import FicheroAPIClient
import OSLog
import SwiftUI

#if os(macOS)

// MARK: - LibraryWindow

/// Main window view - simplified to just track one library per window
struct LibraryWindow: View {
    @Environment(LibraryManager.self) var libraryManager
    @Environment(AppState.self) var appState
    @Environment(ViewSettings.self) var viewSettings

    // internal (not private) so the same-type extension in LibraryWindow+Actions.swift can reach it
    @State var windowState: WindowState

    // App-wide workflow execution observer (uses @Observable, not ObservableObject)
    @State private var executionObserver = WorkflowExecutionObserver()

    // Observed so the first-run sheet binding is reactive to completion.
    private let featureManager = FeatureManager.shared

    @State private var hasInitialized = false
    @State private var showingFileImporter = false
    // ponytail: NEVER auto-present a sheet in the same update cycle that flips
    // `isBackendRunning` — that's when DocumentTabView swaps ContentView in and
    // the window's NSToolbar does its FIRST full layout. Presenting mid-layout
    // re-enters the toolbar update and double-inserts an item → EXC_BREAKPOINT
    // in -[NSToolbar _insertNewItemWithItemIdentifier:…] (#3163, same class as
    // the AddProvider first-launch crash fixed in AppState.loadProviders).
    // This flag trails backend-ready by a settle beat (see the .task in `body`)
    // so the first-run sheet can only present AFTER that first toolbar layout.
    @State private var firstRunSheetArmed = false
    @State var hostWindow: NSWindow?
    @SceneStorage("libraryWindow.libraryId") var persistedLibraryId: String?

    // #2273 per-window state keys for duplicate-window restore and capture.
    // ContentView owns the live state; LibraryWindow just mirrors it.
    @SceneStorage("selectedSidebarItem") var sceneSelectedItemId: String?
    @SceneStorage("viewModeType") var sceneViewModeType: String = "library"
    @SceneStorage("viewModeItemId") var sceneViewModeItemId: String?

    @Environment(\.openWindow) var openWindow
    // #4064: the app-scoped retry entry point threaded down from the app root
    // (see FicheroApp.libraryWindowRoot). The Retry/Quit modal reuses it so a
    // mid-session drop never re-implements the connect sequence.
    @Environment(\.engineRetry) private var engineRetry

    /// Seed handed to a window opened via `openWindow(value: WindowSeed)`
    /// (Duplicate Window, #2262). `nil` for the primary / File ▸ New Window
    /// path, which keeps its existing pending-library + restore behavior.
    let seed: WindowSeed?

    let libraryWindowLogger = Logger(subsystem: "app.fichero.fichero", category: "LibraryWindow")

    init(seed: WindowSeed? = nil) {
        self.seed = seed
        _windowState = State(wrappedValue: WindowState(libraryId: UUID()))
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
        .focusedSceneValue(
            \.openLibraryAction, FocusedLibraryAction(isEnabled: true, run: { showingFileImporter = true })
        )
        .focusedSceneValue(\.newWindowAction, FocusedLibraryAction(isEnabled: true, run: { handleNewWindow() }))
        .focusedSceneValue(\.duplicateWindowAction, duplicateWindowAction)
        .focusedSceneValue(\.newLibraryAction, FocusedLibraryAction(isEnabled: true, run: { handleNewLibrary() }))
        .focusedSceneValue(\.saveLibraryAction, FocusedLibraryAction(isEnabled: true, run: { handleSaveLibrary() }))
        .focusedSceneValue(\.closeLibraryAction, closeLibraryAction)
        // Titlebar tracks the open library so the window title matches its
        // proxy icon (representedURL, set in syncHostWindowMetadata) — macOS
        // convention (#2489). Empty when no library is open. Folder/document
        // selection in the subtitle is a follow-up; ContentView still owns the
        // in-window breadcrumb context.
        .navigationTitle(windowState.library?.displayName ?? "")
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
            .environment(appState.providerService)
        }
        // First-run onboarding (#1947 — sole first-run path, replaces ContentView sheet).
        // It opens once the backend is reachable and stays up until Finish, even if a
        // library is assigned while the user moves through the onboarding steps.
        // Gated on `firstRunSheetArmed` so it never presents in the same update
        // cycle that mounts ContentView / first-populates the NSToolbar (#3163).
        .sheet(isPresented: Binding(
            get: { firstRunSheetArmed && appState.isBackendRunning && !featureManager.firstRunCompleted },
            set: { if !$0 { featureManager.firstRunCompleted = true } }
        )) {
            FirstRunWindow()
                .environment(appState)
        }
        // #4064: the supervised backend dropped AND auto-restart ran out — show a
        // MODAL Retry/Quit over the live main GUI (the toolbar popover stays for
        // the in-flight failure, but a mid-session drop that exhausted restarts
        // needs a blocking decision, not a quiet toolbar item). Retry reuses the
        // one `engineRetry` entry point; Quit is user-chosen terminate (only an
        // app-chosen terminate is banned, #3042). Never shown in the release/
        // embedded build's normal path — the spawn supervisor auto-restarts
        // transparently before this flag ever flips.
        .alert(
            "Fichero Engine Couldn't Restart",
            isPresented: Binding(
                get: { appState.showBackendDropModal },
                set: { appState.showBackendDropModal = $0 }
            )
        ) {
            Button("Retry") {
                appState.showBackendDropModal = false
                Task { await engineRetry?() }
            }
            Button("Quit Fichero", role: .destructive) {
                appState.showBackendDropModal = false
                #if canImport(AppKit)
                NSApplication.shared.terminate(nil)
                #endif
            }
        } message: {
            Text("The Fichero engine stopped and couldn't restart automatically. Retry to try again, or quit.")
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
        // Arm (never disarm) the first-run sheet ONE SETTLE BEAT after
        // backend-ready, so the sheet misses the NSToolbar's first-layout
        // window that ContentView's mount kicks off in the same cycle the
        // `isBackendRunning` flip renders (#3163 re-entrant double-insert
        // crash). `.task(id:)` also runs on appear, covering the Debug case
        // where the external engine is already up before this window exists.
        .task(id: appState.isBackendRunning) {
            guard appState.isBackendRunning, !firstRunSheetArmed else { return }
            try? await Task.sleep(for: .seconds(1))
            guard !Task.isCancelled else { return }
            firstRunSheetArmed = true
        }
    }

}

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
