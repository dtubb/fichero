## Xcode

You are currently being called from inside Xcode, the IDE for Apple programming languages and platforms. As a result, you should prefer to use tools from the "xcode-tools" MCP server whenever possible.

You can use any other tools you need to, but you should probably be able to get the majority of the information you need about this project without using them. In particular, take special care to avoid using command line tools like `ls` or `find` just to learn basic information about the project or its contents. The user may be prompted to approve every single one of those command line invocations, so it's best to use them sparingly.

## Apple Developer Documentation

Use the `DocumentationSearch` MCP command from "xcode-tools" to search for the latest Apple developer documentation for Apple frameworks. The tool runs locally, and gives compact results very quickly. It often has more detailed and newer information than your training data.

Key new terms that you are unlikely to know about and you MUST ALWAYS search for if referenced are:

- Liquid Glass - this is a new design system.
- FoundationModels - this is a new machine learning framework using on-device models, with new macros for structured generation of types.
- SwiftUI is always evolving, particularly around things you may have previously used with view representables. Don't assume you know the latest way of doing anything.

There will be new APIs and frameworks beyond your training data, so use `DocumentationSearch` liberally.

If you can't find an implementation of something mentioned in the project, then assume it is new API that you haven't heard of, and use the `DocumentationSearch` tool to find details.

## Build Commands

Use the `BuildProject` MCP command from "xcode-tools" to build the project.

## Limiting Changes to the Requested Task

Be sure to limit your changes to the things that I ask for. For example, if I ask you to add a button, don't make unrelated changes to other parts of the project.

## Code Style Guidelines

- **Naming**: PascalCase for types, camelCase for properties/methods
- **Properties**: Use `@State private var` for SwiftUI state, `let` for constants
- **Structure**: Conform views to `View` protocol, define UI in `body` property
- **Formatting**: 4-space indentation, clear method separation
- **Imports**: Simple imports at top of file (SwiftUI, Foundation)
- **Types**: Leverage Swift's strong type system, avoid force unwrapping
- **Architecture**: Follow SwiftUI patterns with clear separation of concerns. Avoid using the Combine framework and instead prefer to use Swift's async and await versions of APIs instead.
- **Comments**: Add descriptive comments for complex logic or non-obvious code
- **Testing** Use the Testing framework for unit test and XCUIAutomation framework for UI tests (https://developer.apple.com/documentation/testing/)

## Validating your work

**The three-leg Swift check is mandatory for every SwiftUI change. Run ALL three in this order before declaring work complete:**

1. **SwiftLint** — `swiftlint lint fichero-swiftui/fichero-swiftui/` from the shell. Must be clean (zero warnings/errors) before anything else runs. Hard-rule: lint-clean commits.
2. **Build** — `BuildProject` (or `xcodebuild … build` from the shell). Must succeed with no errors. Warnings should be addressed or explicitly acknowledged.
3. **Unit tests** — `RunAllTests` on the full FicheroTests suite (~220 tests). **Required, not optional.** If the full suite is slow for iteration, use `RunSomeTests` while developing, but `RunAllTests` must pass before you commit.

A build log alone is not evidence of done. A green test run alone is not evidence of done. All three legs must pass. Then add a peekaboo visual check if the change affects rendered UI pixels.

**Primary tools (run every time, in the order above):**

- `XcodeRefreshCodeIssuesInFile` — fast "live" diagnostics from Xcode for compiler errors in a single file (types, hallucinated APIs, missing imports). Completes in seconds. Useful for inner-loop iteration *before* running BuildProject, but does **not** substitute for a full build.

- `BuildProject` — full Xcode build. Catches errors that `XcodeRefreshCodeIssuesInFile` misses (linking, cross-file type resolution, resource compilation). Slower, but authoritative.

- `RunAllTests` — the full FicheroTests suite. **Required before completing any SwiftUI task.** No exceptions. If only a subset is relevant during development, iterate with `RunSomeTests` (`targetName` + `testIdentifier`), but `RunAllTests` must pass at least once before commit.

- `GetBuildLog` / `XcodeListNavigatorIssues` — read on build/test failure to diagnose. Also useful for surfacing warnings that didn't fail the build but still need addressing.

- SwiftLint (`swiftlint lint fichero-swiftui/fichero-swiftui/`) — run from the shell. The Xcode MCP does not run SwiftLint for you.

**Experimental / exploratory:**

- `ExecuteSnippet` - A fast, lightweight tool that runs new code in the context of a given file, sort of like a special Swift REPL environment. This is often much faster than unit tests or full runs, but code executed here is only temporary. Use this to try out a new idea or see how a piece of code in the project works.

- `RenderPreview` - Render a `#Preview` to get a visual snapshot. Useful for static-UI verification, but previews that depend on backend (`@EnvironmentObject var appState`) time out — make previews self-contained with mock data.

**Visual verification (Peekaboo MCP) — for the running app, not Xcode itself:**

Unit tests catch logic regressions; they don't catch UI regressions (wrong highlight color, missing drop outline, layout overflow). After building and running Fichero, use peekaboo to screenshot the real app and verify the rendered UI:

- `mcp__peekaboo__list` with `app: "Fichero"` — find Fichero's windows.
- `mcp__peekaboo__image` with `app_target: "Fichero"`, `capture_focus: "background"`, `path: "/tmp/fichero-<feature>.png"` — screenshot without stealing focus.
- `mcp__peekaboo__see` — screenshot plus element map (`B1`, `T1`, …) for `click`/`type`/`drag` follow-ups.

After capture, `Read` the PNG directly — Claude Code displays images into context. This is more reliable than peekaboo's inline vision-model description (the AI caption can hallucinate file paths and compile details that aren't on screen).

`path` is a *prefix*, not a filename — if Fichero has multiple windows, you get one PNG per window with a title/index suffix. Target a single window or use `frontmost` to get exactly one file.
