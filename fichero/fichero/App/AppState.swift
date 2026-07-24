import FicheroAPIClient
import Foundation
import Observation
import OSLog
#if canImport(AppKit)
import AppKit
#endif
import SwiftUI

enum SettingsTab: Hashable {
    // Per-view settings sections (#3680): one per major view surface.
    case libraryView
    case previewView
    case readerView
    case inspectorView
    case aiModels
    case mcp
    case integrations
    case general
    case engine
    case connect
    case backend
    case users
    case capture
    case about
    case history
    case backups
}

/// Global app state including backend connection and provider management
@MainActor
@Observable
class AppState {
    // MARK: - Backend State

    /// The one backend-usability owner (#3107). The five booleans below are now
    /// read-only shims over `engine.phase`, kept under their legacy names so the
    /// ~20 call sites reading `appState.isBackendRunning` (and friends) keep
    /// working while the source of truth lives in `EngineSession`. Both are
    /// `@Observable`, so a view reading `appState.isBackendRunning` transitively
    /// tracks `engine.phase` and re-renders automatically (#2960) — no manual
    /// change forwarding needed.
    let engine = EngineSession()

    /// Every live backend session (#3112) — the loopback engine `engine` plus
    /// any remote hosts, keyed by host. `engine` is seeded as the default
    /// session so `sessions.activeSession === engine` today; the registry is
    /// the seam for connecting to remote Macs at the same time (#2861/#2883).
    @ObservationIgnored lazy var sessions = EngineSessionRegistry(defaultSession: engine)

    /// Engine is up, authenticated, and usable. Backed by `engine.phase == .ready`.
    var isBackendRunning: Bool { engine.isReady }
    /// Engine answers health checks but REJECTS the app's token (HTTP 401/403) —
    /// the state that used to blank the window with silent 401s (#2864).
    var authBroken: Bool { engine.isAuthRejected }
    /// Human-readable cause for the current unreachable/authBroken/failed state
    /// (port occupied by PID / auth rejected / probe failed), shown full-window.
    var backendDiagnosis: String? { engine.diagnosis }
    /// Alias of `backendDiagnosis` — both used to hold the same message; the
    /// single `engine.diagnosis` now backs them (connection view reads either).
    var backendError: String? { engine.diagnosis }
    var documentCount: Int = 0  // Note: Now tracks active libraries count in multi-library architecture
    var backendVersion: String?
    var backendAccessError: AccessError?
    /// True while starting/probing. Backed by `engine.phase == .starting`.
    var isCheckingBackend: Bool { engine.isChecking }
    /// Count of consecutive heartbeat failures since the last successful
    /// ping. Used to avoid UI thrash on transient blips — the offline
    /// banner flips only after the count crosses `offlineFlipThreshold`.
    var heartbeatFailureCount: Int = 0
    let offlineFlipThreshold: Int = 2

    /// Route a mid-session supervised-engine drop back to the app-scoped
    /// lifecycle controller (#4064). Set by `EngineLifecycleController` at
    /// launch; the heartbeat calls it instead of surfacing a manual-CLI
    /// diagnosis — the controller reuses the existing spawn supervisor (#2611)
    /// to auto-restart the embedded backend with bounded retries + backoff,
    /// and only shows a Retry/Quit modal once those retries run out. nil in
    /// previews / tests / the inert host (no controller wired) — the heartbeat
    /// then falls through to a generic, dev-command-free diagnosis.
    /// Plumbing, not observed UI state: exclude from @Observable tracking.
    @ObservationIgnored var onSupervisedBackendDropped: (@MainActor () async -> Void)?

    /// True when the supervised backend dropped AND auto-restart attempts
    /// were exhausted — the Retry/Quit modal is presented over the live main
    /// GUI (#4064), never a full-window takeover. Cleared by Retry (re-run the
    /// connect sequence) or Quit (terminate). Observed by the main window's
    /// `.alert`, so it lives on the @Observable surface.
    var showBackendDropModal: Bool = false
    // Plumbing, not observed UI state — exclude from @Observable tracking, and
    // `nonisolated(unsafe)` so `deinit` (nonisolated in Swift 6) can cancel it
    // (only mutated on the main actor; `Task.cancel()` is safe from anywhere).
    @ObservationIgnored nonisolated(unsafe) var heartbeatTask: Task<Void, Never>?

    // MARK: - Provider Management

    var providers: [Components.Schemas.ProviderResponse] = []
    var showAddProvider: Bool = false
    var hasCheckedProviders: Bool = false
    var isFirstLaunchProviderSetup: Bool = false  // True when showing Add Provider on first launch

    // MARK: - MCP Server Management

    var selectedSettingsTab: SettingsTab = .aiModels

    /// A `fichero://pair` link the user opened, waiting for them to confirm (#3788).
    ///
    /// A tapped link must NEVER pair silently: it repoints this Mac at a remote host,
    /// which is a trust decision. So the link only PREFILLS the existing Mac pairing
    /// field, and the user still presses Connect — the same confirm-before-pair shape
    /// iOS has. Cleared once consumed.
    var pendingPairingInvite: String?

    var showMCPServers: Bool = false {
        didSet {
            guard showMCPServers else { return }
            openSettings(tab: .mcp)
            showMCPServers = false
        }
    }

    // MARK: - Integrations (Hazel-like folder/app observers)

    var showFolderWatchers: Bool = false {
        didSet {
            guard showFolderWatchers else { return }
            openSettings(tab: .integrations)
            showFolderWatchers = false
        }
    }
    var showAppObservers: Bool = false {
        didSet {
            guard showAppObservers else { return }
            openSettings(tab: .integrations)
            showAppObservers = false
        }
    }
    var showAutomationRules: Bool = false {
        didSet {
            guard showAutomationRules else { return }
            openSettings(tab: .integrations)
            showAutomationRules = false
        }
    }

    // MARK: - Services

    let apiClient = APIClient()  // App-wide APIClient for legacy services
    let ficheroClient = FicheroClient(baseURL: EngineConfig.host, transportMode: EngineConfig.transportMode)  // App-wide generated client
    let providerService: ProviderAPIService  // Public for @EnvironmentObject injection
    let mcpService: MCPService  // Public for @EnvironmentObject injection
    let modelService: ModelService  // Public for @EnvironmentObject injection (HuggingFace browsing)
    let usersStore: UsersStore  // Public for Settings → Users tab
    let sessionStore: SessionStore  // Public for the login gate (#2021/#2022)
    let identityStore: IdentityStore  // Public for the access UX (F5): who am I / owner?
    let localInferenceStore: LocalInferenceStore  // Public for Settings → Local LLM tab (#3120)
    let appleAvailabilityStore: AppleAvailabilityStore  // FirstRun + provider rows (#3121/#3118)
    let kgQueryStore: KGQueryStore  // Public for SPARQL console (#3298); only endpoint accessor (#1863)
    let logger = Logger(subsystem: "app.fichero.fichero", category: "AppState")

    // MARK: - Initialization

    init() {
        // Opens the whole-launch signpost interval; ContentView's first frame
        // closes it. The milestone's elapsed value IS the pre-main cost (dyld +
        // static init), which nothing measured before (#3946).
        LaunchProfile.beginLaunch()
        LaunchProfile.milestone("AppState.init entry")
        // Initialize services with app-wide clients
        self.providerService = ProviderAPIService(ficheroClient: ficheroClient)
        self.mcpService = MCPService(apiClient: apiClient)
        self.modelService = ModelService(ficheroClient: ficheroClient)
        self.usersStore = UsersStore(client: ficheroClient)
        self.sessionStore = SessionStore(client: ficheroClient)
        self.identityStore = IdentityStore(client: ficheroClient)
        self.localInferenceStore = LocalInferenceStore(client: ficheroClient)
        self.appleAvailabilityStore = AppleAvailabilityStore(client: ficheroClient)
        self.kgQueryStore = KGQueryStore(client: ficheroClient)
        LaunchProfile.milestone("AppState.init services ready")
        // #2960: engine is `@Observable`; the computed backend shims read
        // `engine.phase` directly, so views observing them track the engine
        // transitively. The former `objectWillChange` re-publish is retired.
    }

    deinit {
        heartbeatTask?.cancel()
    }
}
