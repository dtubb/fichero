# Validation Pipeline

Run all repo validation checks from repo root:

```bash
./fichero-engine/scripts/validate_repo.sh
```

Checks included:
- SwiftLint (`fichero/fichero/`)
- Xcode build (`fichero/fichero.xcodeproj`)
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
- SwiftLint reports many existing warnings in hand-written Swift files (non-blocking in current script).

Current validation status:
- Xcode build: passing
- Xcode test target compile: passing (`build-for-testing`)
- Python unit tests: passing (`787 passed, 16 skipped`)
- OpenAPI sync + parity: passing

Pylint baseline policy:
- `validate_repo.sh` runs `pylint --errors-only` with `fichero-engine/.pylintrc`.
- Global `no-member` is not disabled; use narrow inline suppressions only for dynamic runtime APIs.
