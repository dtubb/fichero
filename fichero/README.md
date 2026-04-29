# fichero

SwiftUI macOS frontend for Fichero.

## What lives here
- `fichero.xcodeproj`: Xcode project
- `fichero/`: app source code, resources, services, views
- `fichero-api-client/`: generated Swift OpenAPI client package
- `fichero-tests/`, `fichero-ui-tests/`: test target source folders

## Build
From repo root:

```bash
xcodebuild -project fichero/fichero.xcodeproj -scheme Fichero -configuration Debug build
```

## Lint
From repo root:

```bash
swiftlint lint fichero/fichero/
```

## Notes
The app expects the backend at `http://localhost:8765` in local development.
Run `fichero-engine/scripts/sync_openapi_schema.sh` after backend API changes to refresh the Swift package schema consumed by the app.

Sparkle updater release setup notes:
- `fichero/docs/sparkle-release.md`
