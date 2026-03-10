# fichero-swiftui

SwiftUI macOS frontend for Fichero.

## What lives here
- `fichero-swiftui.xcodeproj`: Xcode project
- `fichero-swiftui/`: app source code, resources, services, views
- `fichero-api-client/`: generated Swift OpenAPI client package
- `fichero-swiftui-tests/`, `fichero-swiftui-ui-tests/`: test target source folders

## Build
From repo root:

```bash
xcodebuild -project fichero-swiftui/fichero-swiftui.xcodeproj -scheme Fichero -configuration Debug build
```

## Lint
From repo root:

```bash
swiftlint lint fichero-swiftui/fichero-swiftui/
```

## Notes
The app expects the backend at `http://localhost:8765` in local development.
Run `fichero-api/scripts/sync_openapi_schema.sh` after backend API changes to refresh the Swift package schema consumed by the app.

Sparkle updater release setup notes:
- `fichero-swiftui/docs/sparkle-release.md`
