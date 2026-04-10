---
description: Swift/Xcode project conventions for Claude Code agents. Reference doc — not user-invocable.
---

# Swift / Xcode Project Principles

## Stack

| Component | Tool | Notes |
|---|---|---|
| UI | SwiftUI | Declarative views. `@State`, `@Binding`, `@Environment`. No Combine |
| Concurrency | async/await + Actors | Swift structured concurrency. Never Combine for new code |
| Testing | XCTest | Unit + integration. `swift test` for SPM, Xcode test navigator for .xcodeproj |
| Linting | SwiftLint | `swiftlint lint` before every commit. Fix violations, don't suppress inline |
| Package manager | Swift Package Manager | `Package.swift` for daemons/libraries. Xcode projects for apps |
| Build | Xcode / `swift build` | `swift build` for SPM targets. Xcode (Cmd+B) for app targets |

## Project Structure

### SPM Daemon / Library
```
Sources/
  App/              # Entry point (main.swift)
  Config/           # Configuration, settings
  <Module>/         # Feature modules (one concern per directory)
Tests/
  <Suite>Tests/     # Test suites, mirroring source modules
Package.swift       # Dependencies, targets, Swift language mode
```

### Xcode App (SwiftUI)
```
<AppName>/
  <AppName>App.swift    # @main entry point
  Views/                # SwiftUI views (one per file, small bodies)
  Models/               # Data models, observable objects
  Services/             # Network, storage, business logic
  Settings/             # Preferences UI
<AppName>.xcodeproj     # Xcode project file
```

## Swift Style

| Convention | Rule |
|---|---|
| Types | `PascalCase` |
| Properties, methods | `camelCase` |
| Indentation | 4 spaces |
| Force unwrap (`!`) | Never, except known-safe system paths |
| Imports | Minimal — only what the file needs |
| `let` vs `var` | Prefer `let`. Immutability by default |
| Dead code | Delete it. No commented-out code |

## Swift Concurrency

- Use `async/await` for all asynchronous work. No completion handlers in new code.
- Use `Actor` for shared mutable state. Actors own their state — don't pass mutable references across isolation boundaries.
- Swift 6 strict concurrency where possible. If a target needs `[String: Any]` across boundaries, document why it uses Swift 5 mode.
- `Sendable` compliance is enforced at compile time in strict mode. Design types to be `Sendable` from the start.
- Structured concurrency (`TaskGroup`, `async let`) over unstructured `Task {}` where possible.

## SwiftUI Patterns

- Use SwiftUI idioms: `@State`, `@Binding`, `@Environment`, `@Observable`.
- Keep view bodies small — extract subviews when a body exceeds ~40 lines.
- Prefer system components (`Toggle`, `Picker`, `Form`, `List`) before building custom UI.
- Support both light and dark mode. Use semantic colors (`Color.primary`, `Color.secondary`).
- Support Dynamic Type for text.
- `@ViewBuilder` helpers for conditional content.
- No stale state — if data changes externally, the view must reflect it.

## Error Handling

- Each module defines its own error enum (e.g., `DaemonError`, `ClientError`, `QueueError`).
- Error enums are `Sendable`.
- Conform to `LocalizedError` when the error message is user-facing.
- Never throw generic `NSError` or bare strings.
- Guard clauses over nested `if/else`. Early return on failure.

## MCP Server Integration

For projects that expose tools via the Model Context Protocol:

- **ToolProvider protocol**: Each integration conforms to a `ToolProvider` protocol defining `tools`, `canHandle()`, and `handle()`.
- **Provider registry**: Providers register in a central registry. Tool dispatch goes through the registry.
- **Execution lanes**: Serialize writes within an app, parallelize across apps. Concurrent reads where safe.
- **Input validation**: Validate all external input (JSON depth limits, request size caps, path validation).
- **Rate limiting**: Per-client rate limits on the socket server.
- **Security**: Unix socket permissions `0600`. No shell interpolation — subprocess args passed explicitly. Log redaction for sensitive fields.
- **Schema validation**: `smoke-validate-tools.sh` or equivalent to confirm tool schemas are correct.

## Testing

- `swift test` for SPM packages. Xcode test navigator for app targets.
- Unit tests mock external dependencies. Keep them fast.
- Integration tests that need external apps (Tinderbox, etc.) skip gracefully when unavailable.
- A flaky test is worse than no test. Fix or remove immediately.
- Test new tool providers for: registration, capability classification, policy gating, failure modes.
- Manual QA for UI paths — automated tests cover the backend, human eyes cover the frontend.

## Xcode Conventions

- **Scheme**: One scheme per major target (app, daemon, tests).
- **Build phases**: Lint as a build phase (SwiftLint run script). Schema export if applicable.
- **Signing**: All builds codesigned. `--deep --strict` for distribution.
- **Minimum deployment**: macOS 14 (Sonoma) unless the project specifies otherwise.
- **Versioning**: `MARKETING_VERSION` (CFBundleShortVersionString) + `CURRENT_PROJECT_VERSION` (monotonic build number).
- **App Support**: `~/Library/Application Support/<AppName>/` for runtime data.
- **Logs**: `~/Library/Logs/<AppName>/` for log files.

## Logging

- Logging is best-effort. A logging failure must never cause an operation to fail.
- Redact sensitive inputs before logging (tokens, passwords, authorization headers).
- Structured logging (JSON) for machine-parseable output.

## Build, Test, Lint — Quick Reference

```bash
# SPM
swift build                    # Build
swift test                     # Test
swiftlint lint                 # Lint
swiftlint lint --fix           # Auto-fix

# Xcode
# Cmd+B to build, Cmd+U to test
xcodebuild -scheme <Scheme> build
xcodebuild -scheme <Scheme> test
```

## What Good Swift Looks Like

- Functions do one thing. If it needs a comment to explain, break it up.
- Guard clauses over nested `if/else`. Early return on failure.
- Name things for what they mean. `isConnected` not `connectionBoolFlag`.
- No dead code. No commented-out code. Delete what's not needed.
- Actors own their state. Don't pass mutable references across isolation boundaries.
- Zero external dependencies unless there's a compelling reason. The answer is almost always "no."
- Prefer `let` over `var`. Immutability by default.
