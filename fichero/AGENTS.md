# fichero — SwiftUI app

This subtree is the native client. It renders UI, owns window state, and talks to the
engine over pinned HTTPS loopback. Engine logic stays in `fichero-engine/`.

## What lives here

- `fichero/` — app source (`App/`, `Views/`, `Models/`, `Services/`, `Intents/`)
- `fichero-api-client/` — generated Swift OpenAPI client package
- `fichero-tests/`, `fichero-ui-tests/` — test targets
- `fichero.xcodeproj` — Xcode project

## Hard rules for this subtree

- Start the backend with `bash fichero-engine/scripts/start_backend.sh`. The app pins `https://127.0.0.1:8765` fail-closed, so plain HTTP is not a valid dev setup.
- Lint touched Swift with `swiftlint lint fichero/fichero/`. The manager owns the full Xcode build and test gate.
- `fichero-api-client/` is generated. Do not hand-edit it. If backend routes or schema change, run `fichero-engine/scripts/sync_openapi_schema.sh`.
- `fichero/fichero/Services/*Generated.swift` files are hand-written wrappers despite the name. When building request bodies there, use the typed `Components.Schemas.*` fields, not `additionalProperties`.
- New `.swift` files for the main app target must be registered with `ruby scripts/add-swift-file.rb <path>`.

## Read next

- Repo-wide workflow and verification: [../AGENTS.md](../AGENTS.md)
- App layout and current surfaces: [README.md](README.md)
- SwiftUI conventions: [../docs/contributor/swiftui-development-standards.md](../docs/contributor/swiftui-development-standards.md)
- OpenAPI round-trip contract: [../docs/contributor/openapi-and-clients.md](../docs/contributor/openapi-and-clients.md)
- Observable data layer: [../docs/architecture/swiftui/observable_data_layer.md](../docs/architecture/swiftui/observable_data_layer.md)
