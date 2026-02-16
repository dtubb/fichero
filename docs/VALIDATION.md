# Validation Pipeline

Run all repo validation checks from repo root:

```bash
./fichero-api/scripts/validate_repo.sh
```

Checks included:
- SwiftLint (`fichero-swiftui/fichero-swiftui/`)
- Xcode build (`fichero-swiftui/fichero-swiftui.xcodeproj`)
- Xcode tests
- `pylint --errors-only` for backend packages
- Python unit tests
- OpenAPI sync + parity check between backend contract and Swift package schema

Prerequisites:
- `swiftlint` installed and in `PATH`
- Xcode command line tools available (`xcodebuild`)
- Python venv at `.venv/` with backend dependencies installed
- `briefcase` installed if OpenAPI sync dependencies require full backend environment

Known current blockers (as of 2026-02-16):
- Swift tests fail due to generated type mismatch in test code (e.g. `Components.Schemas.NodeDef`).
- SwiftLint reports existing violations in generated and hand-written Swift files.
- `pylint --errors-only` reports existing backend errors.
- Python unit test suite has existing failures/errors unrelated to folder restructure.
