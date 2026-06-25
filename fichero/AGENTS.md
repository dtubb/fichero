# fichero — SwiftUI app

This folder is the native client. It renders UI, owns window state, and talks to the
backend over pinned HTTPS loopback. The app overview lives in the top-level
[README](../README.md); the SwiftUI-specific docs are under
[docs/architecture/swiftui/](../docs/architecture/swiftui/).

## Keep in mind

- Start the backend with `bash fichero-engine/scripts/start_backend.sh` before testing app behavior.
- Run `swiftlint lint fichero/fichero/` on touched Swift files.
- New `.swift` files must be registered with `ruby scripts/add-swift-file.rb <path>`.
- After backend API/schema changes, sync the OpenAPI contract artifacts before committing.
- Keep generated OpenAPI client code in `fichero/fichero-api-client/` untouched by hand.
- Sparkle release setup now lives in [docs/release/sparkle-release.md](../docs/release/sparkle-release.md).
