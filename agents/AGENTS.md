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

When validating work and experimenting with ideas in Xcode, you have a number of tools at your disposal, each for specific kinds of situations. **For any SwiftUI change, run all three of the primary checks before declaring work complete: SwiftLint, Build, and Unit Tests.** Then add a visual check with peekaboo if the change affects UI pixels.

**Primary checks (run every time):**

- `XcodeRefreshCodeIssuesInFile` - A fast way to get "live" diagnostics from Xcode about many compiler errors you would normally see in Swift files. While you won't learn about build errors in other files or problems with things like linking, you will often be able to see if types are incorrect/unresolvable, if you have hallucinated/mistyped APIs, or if you've forgotten to import something. Use this to quickly verify your work, since it's not allowed to take more than a couple seconds to run.

- `BuildProject` - Build the project in Xcode. Fully compiles and assembles binaries and resources using Xcode's build system. You can use this to check that work compiles and builds correctly. An extremely powerful tool, but builds can take a long time.

- `RunAllTests` - Run the full FicheroTests suite (~220 tests). **Required before completing any SwiftUI task** — not optional. If only a subset is relevant and the full suite is slow, use `RunSomeTests` with a `targetName` + `testIdentifier`, but run the full suite at least once before committing.

- `GetBuildLog` / `XcodeListNavigatorIssues` - Read these on failure, or to surface warnings that didn't fail the build but still need addressing.

- SwiftLint (`swiftlint lint fichero-swiftui/fichero-swiftui/`) - Run from the shell before every commit. The project hard rule is lint-clean commits.

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
