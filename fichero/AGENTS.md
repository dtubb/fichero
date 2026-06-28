# fichero — SwiftUI app

This folder is the native client: it renders UI, owns window state, and talks to the
engine over pinned HTTPS loopback. The logic lives in the engine, not here.

**Canonical docs (do not duplicate here):**
- Operational manual + hard rules: root [AGENTS.md](../AGENTS.md) — build/lint/test,
  the `add-swift-file.rb` registration rule, OpenAPI sync, commit attribution.
- Developer docs: [docs/contributor/](../docs/contributor/).
- User manual: [docs/user/](../docs/user/).
- This component's orientation, source layout, and key concepts: [README](README.md).
- Swift conventions and the API round-trip contract:
  [docs/architecture/swiftui/](../docs/architecture/swiftui/).

## Component essentials

- Start the engine first: `bash fichero-engine/scripts/start_backend.sh` (serves
  HTTPS; the app pins it fail-closed).
- Lint touched Swift: `swiftlint lint fichero/fichero/`.
