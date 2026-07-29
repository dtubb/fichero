# fichero — SwiftUI app

The native Apple front end for Fichero (macOS, with iOS/iPad as clients that connect to Fichero running on a macOS). The app is a **thin client**: it renders and
accepts input, and talks to the FastAPI engine over pinned HTTPS loopback. The
logic — ingest, search, knowledge graph, workflows — lives in the engine, not
here. See the [top-level README](../README.md) for the whole-system picture, the
root [AGENTS.md](../AGENTS.md) for build/lint/test rules and commit attribution, and
[docs/contributor/](../docs/contributor/) for the developer docs. This file
keeps only what is specific to the app: its layout and key concepts.

## What lives here

| Path | What |
|---|---|
| `fichero.xcodeproj` | Xcode project (main target: `Fichero`) |
| `fichero/` | App source — `App/`, `Views/`, `Models/`, `Services/`, `Intents/`, resources |
| `fichero-api-client/` | Generated Swift OpenAPI client package (`Sources/FicheroAPIClient/` is generated — do not hand-edit) |
| `fichero-tests/`, `fichero-ui-tests/` | Test target source folders |

### Source layout (`fichero/fichero/`)

```
App/            FicheroApp (macOS) + FicheroApp_iOS, AppState, LibraryWindow, window/scene scaffolding
Views/          Feature surfaces across ~19 domains:
  Library/        document browser + PDF/image reading view + tabbed inspector
  Search/         semantic search UI
  Chat/           RAG conversation UI
  Workflow/       visual LangGraph node editor + canvas
  KnowledgeGraph/ entity / claim digests and graph views
  Activity/ Settings/ AIProviders/ Automation/ …
Models/         @Observable domain stores (DocumentStore, WorkflowStore, SidebarState, ObservableDomainStore, …)
Services/       APIClient + hand-written *Generated.swift service wrappers over the OpenAPI client
Intents/        App Intents / Shortcuts
```

## Key concepts

- **Observable stores.** Views observe `@Observable` domain stores (e.g.
  `DocumentStore`, `WorkflowStore`). The store is the single accessor for
  endpoints and the change stream — views never call the API directly. This
  keeps pure-display views, live observers, and multi-window sync on one path.
- **Typed OpenAPI client.** All engine calls go through the generated
  `FicheroAPIClient` package and the `Services/*Generated.swift` wrappers. When
  building a request body, always use the typed `Components.Schemas.*` fields —
  never `additionalProperties` for a declared field (it silently drops writes).
- **Surfaces, not silos.** Library, Reader, Search, Chat, Workflows, and the
  Knowledge Graph are all views onto the same engine-owned data model. The KG is
  backend-owned; the app renders it.
- **HTTPS-only transport.** The app never talks plain HTTP. The default engine
  is `https://127.0.0.1:8765` (the local engine); paired remote hosts (own
  devices / Tailscale) are reached over HTTPS with per-host SPKI certificate
  pinning. In Debug you start the engine yourself (`start_backend.sh`); a Release
  build embeds and spawns it.

## Build & run

First-time setup (Python 3.12, the repo-root `.venv`, the engine) is documented once,
in [CONTRIBUTING.md](../CONTRIBUTING.md). This section assumes it is done.

Open `fichero/fichero.xcodeproj` in Xcode and run the `Fichero` scheme.

- **Debug (⌘R)** expects an engine you started yourself:
  `bash fichero-server/scripts/start_backend.sh` (external, `:8765`).
- **Release** embeds the engine (Briefcase) and spawns it on launch.

Command-line build (from repo root). `-skipPackagePluginValidation` is required — the
OpenAPIGenerator SPM plugin fails without it:

```bash
xcodebuild -project fichero/fichero.xcodeproj -scheme Fichero \
  -configuration Debug -skipPackagePluginValidation build
```

To launch an already-built `.app`, use the helper rather than exec-ing the
binary (direct exec does not draw a window on macOS 26):

```bash
scripts/launch-release.sh          # Release
scripts/launch-release.sh --debug  # Debug
```

## Lint

```bash
swiftlint lint fichero/fichero/
```

## Conventions

The repo-wide rules (registering new `.swift` files with `add-swift-file.rb`, syncing
the OpenAPI schema after backend changes, the three-leg Swift check) live in the root
[AGENTS.md](../AGENTS.md).

## Read next

- Repo-wide workflow and verification: [../AGENTS.md](../AGENTS.md)
- SwiftUI conventions: [../docs/contributor/swiftui-development-standards.md](../docs/contributor/swiftui-development-standards.md)
- OpenAPI round-trip contract: [../docs/contributor/openapi-and-clients.md](../docs/contributor/openapi-and-clients.md)
- Observable data layer: [../docs/contributor/architecture/fichero/observable_data_layer.md](../docs/contributor/architecture/fichero/observable_data_layer.md)
- Sparkle updater release setup: [../docs/contributor/release/sparkle-release.md](../docs/contributor/release/sparkle-release.md)
