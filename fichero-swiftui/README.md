# fichero-swiftui

SwiftUI macOS frontend for Fichero.

## What lives here
- `Fichero.xcodeproj`: Xcode project
- `fichero-swiftui/`: app source code, resources, services, views
- `FicheroAPIClient/`: generated Swift OpenAPI client package
- `FicheroTests/`, `FicheroUITests/`: test targets

## Build
From repo root:

```bash
xcodebuild -project fichero-swiftui/Fichero.xcodeproj -scheme Fichero -configuration Debug build
```

## Lint
From repo root:

```bash
swiftlint lint --path fichero-swiftui/fichero-swiftui/
```

## Notes
The app expects the backend at `http://localhost:8765` in local development.
