# Fichero Feature Flag System Design

## 1. Overview

The feature flag system uses a simple, static approach on both sides:

- **Swift**: A single `FeatureFlags.swift` file with a struct of static `Bool` properties. Views check these at runtime. A `devMode` master toggle flips all dev-only flags at once.
- **Python**: A `feature_flags.py` module with a `FeatureFlags` class whose attributes are populated from environment variables, with coded defaults. The `FICHERO_DEV_MODE` env var activates all dev-only flags.
- **Sync**: A `/api/feature-flags` endpoint returns the backend's active flag state as JSON. The SwiftUI app queries this at startup and merges it into its local `FeatureFlags` singleton, so both sides agree.

This avoids external dependencies (no LaunchDarkly, no database table). Agents toggle flags by setting environment variables or editing a single file.

---

## 2. Swift Implementation

### File: `fichero-swiftui/fichero-swiftui/App/FeatureFlags.swift`

```swift
import Foundation

/// Central feature flag registry.
/// Views check `FeatureFlags.shared.featureChat` etc.
/// Flags default to their release values; `devMode` overrides dev-only flags to true.
final class FeatureFlags: ObservableObject {
    static let shared = FeatureFlags()

    // MARK: - Master Toggle

    /// When true, all DEV-ONLY features are enabled.
    /// Set via Xcode scheme environment variable FICHERO_DEV_MODE=1,
    /// or toggled at runtime from the hidden Settings > Developer menu.
    @Published var devMode: Bool

    // MARK: - Feature Flags (Release defaults)

    // --- ON by default (release-ready) ---
    @Published var featureAIProviders: Bool = true
    @Published var featureActions: Bool = true
    @Published var featureActivity: Bool = true
    @Published var featureAgents: Bool = true
    @Published var featureAutomation: Bool = true
    @Published var featureBatch: Bool = true
    @Published var featureChat: Bool = true
    @Published var featureComponents: Bool = true
    @Published var featureLibrary: Bool = true
    @Published var featureMCPServers: Bool = true
    @Published var featureMenu: Bool = true
    @Published var featureSearch: Bool = true
    @Published var featureSettings: Bool = true
    @Published var featureSheets: Bool = true
    @Published var featureSidebar: Bool = true
    @Published var featureToolbars: Bool = true
    @Published var featureWorkflow: Bool = true
    @Published var featureDocuments: Bool = true
    @Published var featureIngest: Bool = true
    @Published var featureStorage: Bool = true
    @Published var featureProviders: Bool = true
    @Published var featureWorkflowExecution: Bool = true
    @Published var featureArtifacts: Bool = true
    @Published var featureFolders: Bool = true

    // --- DEV-ONLY (off in release, on when devMode is true) ---
    @Published var featureIntegrations: Bool = false
    @Published var featureModelComparison: Bool = false
    @Published var featureSchedules: Bool = false
    @Published var featureTriggers: Bool = false
    @Published var featureChains: Bool = false
    @Published var featureLocalModels: Bool = false
    @Published var featureModels: Bool = false  // HuggingFace models browser

    // MARK: - Init

    private init() {
        // Check for dev mode from environment (Xcode scheme) or UserDefaults
        let envDev = ProcessInfo.processInfo.environment["FICHERO_DEV_MODE"] == "1"
        let defaultsDev = UserDefaults.standard.bool(forKey: "ficheroDevMode")
        self.devMode = envDev || defaultsDev

        if self.devMode {
            applyDevMode()
        }
    }

    /// Enable all dev-only flags.
    func applyDevMode() {
        featureIntegrations = true
        featureModelComparison = true
        featureSchedules = true
        featureTriggers = true
        featureChains = true
        featureLocalModels = true
        featureModels = true
    }

    /// Reset dev-only flags to their release defaults (all off).
    func applyReleaseMode() {
        featureIntegrations = false
        featureModelComparison = false
        featureSchedules = false
        featureTriggers = false
        featureChains = false
        featureLocalModels = false
        featureModels = false
    }

    // MARK: - Backend Sync

    /// Merge flags received from the backend `/api/feature-flags` endpoint.
    /// Backend is authoritative for route-level flags; frontend-only flags are untouched.
    func mergeFromBackend(_ backendFlags: [String: Bool]) {
        // Map Python FEATURE_X naming to Swift property names
        let mapping: [String: WritableKeyPath<FeatureFlags, Bool>] = [
            "FEATURE_DOCUMENTS": \.featureDocuments,
            "FEATURE_SEARCH": \.featureSearch,
            "FEATURE_INGEST": \.featureIngest,
            "FEATURE_STORAGE": \.featureStorage,
            "FEATURE_CHAT": \.featureChat,
            "FEATURE_PROVIDERS": \.featureProviders,
            "FEATURE_WORKFLOWS": \.featureWorkflow,
            "FEATURE_WORKFLOW_EXECUTION": \.featureWorkflowExecution,
            "FEATURE_ARTIFACTS": \.featureArtifacts,
            "FEATURE_BATCH": \.featureBatch,
            "FEATURE_ACTIVITY": \.featureActivity,
            "FEATURE_FOLDERS": \.featureFolders,
            "FEATURE_SETTINGS": \.featureSettings,
            "FEATURE_ACTIONS": \.featureActions,
            "FEATURE_INTEGRATIONS": \.featureIntegrations,
            "FEATURE_MCP_SERVERS": \.featureMCPServers,
            "FEATURE_SCHEDULES": \.featureSchedules,
            "FEATURE_TRIGGERS": \.featureTriggers,
            "FEATURE_CHAINS": \.featureChains,
            "FEATURE_LOCAL_MODELS": \.featureLocalModels,
            "FEATURE_MODEL_COMPARISON": \.featureModelComparison,
            "FEATURE_MODELS": \.featureModels,
        ]

        for (key, keyPath) in mapping {
            if let value = backendFlags[key] {
                self[keyPath: keyPath] = value
            }
        }
    }
}
```

### Usage in Views

Views check flags directly. Example in the sidebar mode picker (where `SidebarMode` cases are listed):

```swift
// In SidebarModePicker or wherever sidebar tabs are built
ForEach(SidebarMode.allCases, id: \.self) { mode in
    if shouldShowSidebarMode(mode) {
        // render tab
    }
}

private func shouldShowSidebarMode(_ mode: SidebarMode) -> Bool {
    let flags = FeatureFlags.shared
    switch mode {
    case .library:    return flags.featureLibrary
    case .search:     return flags.featureSearch
    case .chat:       return flags.featureChat
    case .workflows:  return flags.featureWorkflow
    case .batches:    return flags.featureBatch
    case .automation: return flags.featureAutomation
    case .activity:   return flags.featureActivity
    }
}
```

For menu items in `FicheroApp.swift`:

```swift
// Conditionally show menu items
if FeatureFlags.shared.featureIntegrations {
    Menu("Integrations") {
        Button("Folder Watchers...") { ... }
        Button("App Observers...") { ... }
    }
}
```

### Xcode Scheme Integration

In the "Debug" scheme, add environment variable `FICHERO_DEV_MODE=1` under Run > Arguments > Environment Variables. The "Release" scheme omits it, so dev-only flags stay off.

---

## 3. Python Implementation

### File: `fichero-api/src/fichero/feature_flags.py`

```python
"""
Feature Flags for Fichero API.

Flags are read from environment variables at import time.
Set FICHERO_DEV_MODE=1 to enable all dev-only features.

Individual flags can be overridden:
    FEATURE_INTEGRATIONS=1 fichero serve
"""

import os

def _flag(env_key: str, default: bool) -> bool:
    """Read a boolean flag from environment, with default."""
    val = os.environ.get(env_key)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes")


DEV_MODE = _flag("FICHERO_DEV_MODE", False)


class FeatureFlags:
    """Singleton feature flag registry."""

    # --- ON by default (release-ready routes) ---
    FEATURE_DOCUMENTS: bool = True
    FEATURE_SEARCH: bool = True
    FEATURE_INGEST: bool = True
    FEATURE_STORAGE: bool = True
    FEATURE_CHAT: bool = True
    FEATURE_PROVIDERS: bool = True
    FEATURE_WORKFLOWS: bool = True
    FEATURE_WORKFLOW_EXECUTION: bool = True
    FEATURE_ARTIFACTS: bool = True
    FEATURE_BATCH: bool = True
    FEATURE_ACTIVITY: bool = True
    FEATURE_FOLDERS: bool = True
    FEATURE_SETTINGS: bool = True

    # --- DEV-ONLY (off in release, on when DEV_MODE is true) ---
    FEATURE_ACTIONS: bool = _flag("FEATURE_ACTIONS", DEV_MODE)
    FEATURE_INTEGRATIONS: bool = _flag("FEATURE_INTEGRATIONS", DEV_MODE)
    FEATURE_MCP_SERVERS: bool = _flag("FEATURE_MCP_SERVERS", DEV_MODE)
    FEATURE_SCHEDULES: bool = _flag("FEATURE_SCHEDULES", DEV_MODE)
    FEATURE_TRIGGERS: bool = _flag("FEATURE_TRIGGERS", DEV_MODE)
    FEATURE_CHAINS: bool = _flag("FEATURE_CHAINS", DEV_MODE)
    FEATURE_LOCAL_MODELS: bool = _flag("FEATURE_LOCAL_MODELS", DEV_MODE)

    # --- OFF by default (incomplete/experimental) ---
    FEATURE_MODEL_COMPARISON: bool = _flag("FEATURE_MODEL_COMPARISON", False)
    FEATURE_MODELS: bool = _flag("FEATURE_MODELS", False)

    @classmethod
    def as_dict(cls) -> dict[str, bool]:
        """Return all flags as a dict (for the /api/feature-flags endpoint)."""
        return {
            key: getattr(cls, key)
            for key in sorted(dir(cls))
            if key.startswith("FEATURE_")
        }

    @classmethod
    def is_enabled(cls, flag_name: str) -> bool:
        """Check if a flag is enabled. Raises AttributeError if flag doesn't exist."""
        return getattr(cls, flag_name)


# Convenience alias
flags = FeatureFlags
```

### Conditional Route Registration in `main.py`

Replace the unconditional `app.include_router(...)` block with flag-guarded registration:

```python
from fichero.feature_flags import flags

# Always-on routes
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(ingest.router, prefix="/api/ingest", tags=["ingest"])
app.include_router(storage.router, prefix="/api/storage", tags=["storage"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(providers.router, prefix="/api/providers", tags=["providers"])
app.include_router(workflows.router, prefix="/api/workflows", tags=["workflows"])
app.include_router(workflow_execution.router, prefix="/api/workflow-execution", tags=["workflow-execution"])
app.include_router(artifacts.router, prefix="/api/artifacts", tags=["artifacts"])
app.include_router(batch.router, prefix="/api", tags=["batches"])
app.include_router(activity.router, prefix="/api", tags=["activity"])
app.include_router(folders.router, prefix="/api/folders", tags=["folders"])
app.include_router(settings.router, tags=["settings"])

# Dev-only routes (gated)
if flags.FEATURE_ACTIONS:
    app.include_router(actions.router, prefix="/api", tags=["actions"])
if flags.FEATURE_INTEGRATIONS:
    app.include_router(integrations.router, prefix="/api", tags=["integrations"])
if flags.FEATURE_MCP_SERVERS:
    app.include_router(mcp_servers.router, prefix="/api", tags=["mcp-servers"])
if flags.FEATURE_SCHEDULES:
    app.include_router(schedules.router, prefix="/api", tags=["schedules"])
if flags.FEATURE_TRIGGERS:
    app.include_router(triggers.router, prefix="/api", tags=["triggers"])
if flags.FEATURE_CHAINS:
    app.include_router(chains.router, prefix="/api", tags=["chains"])
if flags.FEATURE_LOCAL_MODELS:
    app.include_router(local_models.router, prefix="/api", tags=["local-models"])

# Off by default (must be explicitly enabled)
if flags.FEATURE_MODEL_COMPARISON:
    app.include_router(model_comparison.router, prefix="/api", tags=["model-comparison"])
if flags.FEATURE_MODELS:
    app.include_router(models.router, prefix="/api/models", tags=["models"])
```

### Agent Toggle Pattern

Agents (Claude Code, Codex) toggle flags by setting env vars before starting the server:

```bash
# Enable everything for development
FICHERO_DEV_MODE=1 uvicorn fichero.api.main:app --reload

# Enable just one specific feature
FEATURE_MODEL_COMPARISON=1 uvicorn fichero.api.main:app --reload

# Production (release defaults)
uvicorn fichero.api.main:app
```

---

## 4. Sync Mechanism

### Endpoint: `GET /api/feature-flags`

Added directly in `main.py` (no separate route file needed):

```python
@app.get("/api/feature-flags")
async def get_feature_flags():
    """Return current feature flag state.

    The SwiftUI app calls this at startup to sync its local flags
    with the backend's active configuration.
    """
    from fichero.feature_flags import flags
    return {
        "dev_mode": flags.DEV_MODE if hasattr(flags, 'DEV_MODE') else False,
        "flags": flags.as_dict(),
    }
```

### Swift Startup Flow

In `FicheroApp.swift`, after the backend health check succeeds, fetch flags:

```swift
// In the .task block of LibraryWindow, after backend starts:
do {
    try await backendService.start()
    logger.info("Backend started successfully")

    // Sync feature flags from backend
    await FeatureFlags.shared.syncFromBackend(baseURL: backendService.baseURL)
} catch {
    logger.error("Failed to start backend: \(error.localizedDescription)")
    await showBackendError(error)
}
```

The `syncFromBackend` method on `FeatureFlags`:

```swift
extension FeatureFlags {
    /// Fetch flags from the backend and merge them.
    func syncFromBackend(baseURL: URL) async {
        guard let url = URL(string: "/api/feature-flags", relativeTo: baseURL) else { return }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let response = try JSONDecoder().decode(FlagResponse.self, from: data)
            await MainActor.run {
                self.mergeFromBackend(response.flags)
            }
        } catch {
            // Non-fatal: keep local defaults if backend sync fails
            Logger(subsystem: "ca.tubb.Fichero", category: "FeatureFlags")
                .warning("Failed to sync feature flags from backend: \(error.localizedDescription)")
        }
    }

    struct FlagResponse: Decodable {
        let dev_mode: Bool
        let flags: [String: Bool]
    }
}
```

### Sync Rules

1. Backend is authoritative for **route-level** flags (if backend says FEATURE_CHAT=false, the Swift app hides Chat UI even if its local default is true).
2. Frontend-only flags (featureComponents, featureToolbars, featureMenu, featureSidebar, featureSheets) have no backend counterpart and are managed locally.
3. Sync happens once at startup. No polling. If the backend restarts with different flags, the user must restart the app (or we add a manual refresh in Settings later).

---

## 5. Complete Feature Matrix

| Feature | Swift Flag | Python Flag | Default (Release) | Default (Dev) | Notes |
|---|---|---|---|---|---|
| **Frontend-only areas** | | | | | |
| AI Providers UI | `featureAIProviders` | -- | ON | ON | Settings sheet for provider config |
| Agents UI | `featureAgents` | -- | ON | ON | Agent configuration views |
| Components | `featureComponents` | -- | ON | ON | Shared UI components |
| Menu | `featureMenu` | -- | ON | ON | App menu bar items |
| Sheets | `featureSheets` | -- | ON | ON | Modal sheet presentations |
| Sidebar | `featureSidebar` | -- | ON | ON | Sidebar navigation chrome |
| Toolbars | `featureToolbars` | -- | ON | ON | Toolbar controls |
| **Shared features (frontend + backend)** | | | | | |
| Documents / Library | `featureLibrary` / `featureDocuments` | `FEATURE_DOCUMENTS` | ON | ON | Core document browsing |
| Search | `featureSearch` | `FEATURE_SEARCH` | ON | ON | Full-text + semantic search |
| Ingest | `featureIngest` | `FEATURE_INGEST` | ON | ON | File import pipeline |
| Storage | `featureStorage` | `FEATURE_STORAGE` | ON | ON | File storage layer |
| Chat | `featureChat` | `FEATURE_CHAT` | ON | ON | RAG conversations |
| Providers | `featureProviders` | `FEATURE_PROVIDERS` | ON | ON | Provider CRUD API |
| Workflows | `featureWorkflow` | `FEATURE_WORKFLOWS` | ON | ON | Workflow definitions |
| Workflow Execution | `featureWorkflowExecution` | `FEATURE_WORKFLOW_EXECUTION` | ON | ON | Running workflows |
| Artifacts | `featureArtifacts` | `FEATURE_ARTIFACTS` | ON | ON | Workflow artifacts |
| Batch | `featureBatch` | `FEATURE_BATCH` | ON | ON | Multi-item batch jobs |
| Activity | `featureActivity` | `FEATURE_ACTIVITY` | ON | ON | Run history / logs |
| Folders | `featureFolders` | `FEATURE_FOLDERS` | ON | ON | Folder hierarchy |
| Settings | `featureSettings` | `FEATURE_SETTINGS` | ON | ON | App settings API |
| Automation UI | `featureAutomation` | -- | ON | ON | Sidebar mode (wraps schedules+triggers) |
| **DEV-ONLY features** | | | | | |
| Actions | `featureActions` | `FEATURE_ACTIONS` | ON (frontend) / DEV (backend) | ON | Frontend ON; backend routes dev-only |
| Integrations | `featureIntegrations` | `FEATURE_INTEGRATIONS` | DEV | DEV | Folder watchers, app observers |
| MCP Servers | `featureMCPServers` | `FEATURE_MCP_SERVERS` | ON (frontend) / DEV (backend) | ON | Frontend settings ON; backend routes dev-only |
| Schedules | `featureSchedules` | `FEATURE_SCHEDULES` | DEV | DEV | Cron-based workflow scheduling |
| Triggers | `featureTriggers` | `FEATURE_TRIGGERS` | DEV | DEV | Event-based workflow triggers |
| Chains | `featureChains` | `FEATURE_CHAINS` | DEV | DEV | Multi-workflow chains |
| Local Models | `featureLocalModels` | `FEATURE_LOCAL_MODELS` | DEV | DEV | Local model management |
| Model Comparison | `featureModelComparison` | `FEATURE_MODEL_COMPARISON` | DEV (frontend) / OFF (backend) | DEV | Side-by-side model output comparison |
| **OFF features** | | | | | |
| Models (HuggingFace) | `featureModels` | `FEATURE_MODELS` | OFF | OFF | HuggingFace model browser; incomplete |

### Notes on the Matrix

- "DEV" means the flag is `false` by default but becomes `true` when `devMode` / `FICHERO_DEV_MODE` is active.
- "OFF" means the flag is `false` even in dev mode; must be explicitly enabled with an individual env var.
- Frontend-only flags (Components, Menu, Sheets, Sidebar, Toolbars) have no backend counterpart because they control pure UI chrome with no API dependency.
- The Actions and MCP Servers rows have a split: the frontend UI is ON in release (the views exist and are stable), but the backend routes are DEV-ONLY (APIs are still being finalized). The sync mechanism handles this -- if the backend disables a route, the frontend will gracefully show "not available" or hide the feature based on the synced flag.

---

## 6. Implementation Tasks

### Phase 1: Core Infrastructure (do first)

1. **Create `fichero-api/src/fichero/feature_flags.py`**
   - Implement the `FeatureFlags` class with all flags and `as_dict()` method.
   - Wire up `_flag()` helper for env var reading.
   - Wire up `DEV_MODE` master toggle.

2. **Add `/api/feature-flags` endpoint to `main.py`**
   - Add the `get_feature_flags()` route.
   - Gate existing `include_router()` calls with flag checks.

3. **Create `fichero-swiftui/fichero-swiftui/App/FeatureFlags.swift`**
   - Implement the `FeatureFlags` class with all flags, `mergeFromBackend()`, and `syncFromBackend()`.
   - Wire up `devMode` from `ProcessInfo` environment and `UserDefaults`.

### Phase 2: Frontend Integration

4. **Wire up flag sync in `FicheroApp.swift`**
   - Call `FeatureFlags.shared.syncFromBackend()` after backend health check passes.
   - Inject `FeatureFlags.shared` as `@EnvironmentObject` on the window group (so views can observe changes).

5. **Gate sidebar modes**
   - In the sidebar mode picker, filter `SidebarMode.allCases` through `FeatureFlags`.
   - Hide automation tab when `featureAutomation` is off, etc.

6. **Gate menu items in `FicheroApp.swift`**
   - Wrap the Integrations submenu, MCP Servers button, and Data menu items (New Comparison, New Chain, New Schedule, New Trigger) in flag checks.

7. **Gate view navigation in `ContentView+Navigation`**
   - When routing to a view mode (e.g., `.comparison`), check its flag first. If disabled, redirect to `.library`.

### Phase 3: Backend Integration

8. **Update `main.py` route registration**
   - Replace unconditional `include_router` calls with flag-gated versions (code shown in Section 3).

9. **Add flag logging on startup**
   - In the `lifespan()` function, log which features are enabled/disabled so operators can verify configuration.

### Phase 4: Developer Experience

10. **Xcode scheme configuration**
    - Add `FICHERO_DEV_MODE=1` to the Debug scheme's environment variables.
    - Document the pattern in the project README or CONTRIBUTING guide.

11. **Add a hidden Developer panel in Settings**
    - A simple list of toggles that maps to `FeatureFlags.shared` properties.
    - Only visible when `devMode` is true.
    - Saves `ficheroDevMode` to `UserDefaults` for persistence across launches.

12. **Backend startup banner**
    - Print a summary of active/inactive flags to the console on startup, e.g.:
    ```
    Feature Flags (dev_mode=True):
      FEATURE_DOCUMENTS: ON
      FEATURE_MODEL_COMPARISON: OFF
      ...
    ```

---

## Design Decisions and Rationale

**Why static bools instead of a database table?**
Feature flags here control code paths, not user-facing A/B tests. They change with deploys or env vars, not at runtime per-user. A database table adds complexity (migration, UI, API) for no benefit at this scale.

**Why not compile-time `#if` flags?**
Compile-time flags require separate builds for different configurations. Runtime bools let us toggle features without recompilation, which is essential for agent-driven development where an agent might enable a feature mid-session.

**Why environment variables on the Python side?**
Environment variables are the standard 12-factor way to configure services. They work with Docker, systemd, launchd, and direct invocation. Agents can set them trivially. No config file to parse or keep in sync.

**Why sync from backend to frontend (not the other direction)?**
The backend is the source of truth for which routes are actually available. If a route is disabled, the frontend must know -- otherwise API calls will 404. Frontend-only flags (UI chrome) do not need to flow to the backend.

**Why not poll for flag changes?**
Flags change when the server restarts (new env vars) or when the user toggles devMode. Both are infrequent. Polling adds network traffic and complexity for near-zero benefit. A manual "refresh flags" button in Developer settings is sufficient for the edge case.
