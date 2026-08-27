# fichero — SwiftUI app

This subtree is the SwiftUI mac, iPad, and iOS app. The app renders UI, owns window state, and talks to the engine over pinned HTTPS loopback. Engine logic stays in `fichero-server/`.

## What lives here

- `fichero/` — app source (`App/`, `Views/`, `Models/`, `Services/`, `Intents/`)
- `fichero-api-client/` — generated Swift OpenAPI client package
- `Tests/Unit/*`, `Tests/UI/*` — test target folders (general/mac/ios/ipad); plans in `Tests/plans/`
- `fichero.xcodeproj` — Xcode project

## Hard rules for this subtree

- First-time setup (Python 3.12, the repo-root `.venv`) is documented once, in
  [../CONTRIBUTING.md](../CONTRIBUTING.md). Do not repeat it here.
- CLI `xcodebuild` needs `-skipPackagePluginValidation`; the OpenAPIGenerator SPM
  plugin fails without it. Prefer the Xcode MCP (`BuildProject`) over raw `xcodebuild`.

- **Run target: `Fichero (Dev Embedded)`** — the app spawns its own bundled engine; stop any hand-started engine first (two engines would contend for one UDS socket). The **Local** schemes (e.g. "Fichero (Dev Local)") are for engine development: start the engine yourself with `bash fichero-server/scripts/start_backend.sh`. Transport is a local Unix domain socket, or HTTPS — `https://127.0.0.1:8765` locally, per-host SPKI certificate pinning for paired remote hosts (own devices / Tailscale). Plain HTTP over TCP is never a valid setup.
- Lint touched Swift with `swiftlint lint fichero/fichero/`. The manager owns the full Xcode build and test gate.
- `fichero-api-client/` is generated. Do not hand-edit it. If backend routes or schema change, run `fichero-server/scripts/sync_openapi_schema.sh`.
- `fichero/fichero/Services/*Generated.swift` files are hand-written wrappers despite the name. When building request bodies there, use the typed `Components.Schemas.*` fields, not `additionalProperties`.
- New `.swift` files for the main app target must be registered with `ruby scripts/add-swift-file.rb <path>`.

## Read next

- Repo-wide workflow and verification: [../AGENTS.md](../AGENTS.md)
- App layout and current surfaces: [README.md](README.md)
- SwiftUI conventions: [../docs/contributor/swiftui-development-standards.md](../docs/contributor/swiftui-development-standards.md)
- OpenAPI round-trip contract: [../docs/contributor/openapi-and-clients.md](../docs/contributor/openapi-and-clients.md)
- Observable data layer: [../docs/contributor/architecture/fichero/observable_data_layer.md](../docs/contributor/architecture/fichero/observable_data_layer.md)
