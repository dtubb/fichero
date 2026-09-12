(AI generated. Not reviewed.)

# iPhone and iPad Interaction Model

This page is a grounded reference for the Apple mobile interaction model as it
exists in the current SwiftUI codebase. "Current" means merged code in
`fichero/fichero/`. "Target" means planned work that is not yet implemented.

## Current Architecture

The shared non-macOS library surface is `LibraryWorkspaceRoot`, which wraps the
workspace in `AdaptiveAppleShellHost` and then mounts `DocumentTabView`
(`fichero/fichero/Views/Library/LibraryWorkspaceRoot.swift:34-37`,
`52-103`). macOS does not use this direct path; `LibraryWindow` is fenced by
`#if os(macOS)` and wraps the same workspace separately
(`fichero/fichero/App/LibraryWindow.swift:1-14`, `78-107`).

On compact width, `AdaptiveAppleShellHost` adds an outer `NavigationStack`
around the entire content tree. On regular width, it leaves the content alone
(`fichero/fichero/Views/AdaptiveAppleShellHost.swift:29-38`). Inside that host,
`ContentView` still builds a `NavigationSplitView` with a sidebar column and a
detail column, plus `preferredCompactColumn`
(`fichero/fichero/Views/Shell/ContentView/ContentView.swift:31-35`, `93`,
`461-489`). The compact path therefore does not replace the split shell; it
wraps it.

The detail column still carries desktop-style chrome. `detailShellColumn` always
stacks `detailTabStrip`, `detailLocationPathBar`, `centerContent`, and
`detailStatusPathBar`
(`fichero/fichero/Views/Shell/ContentView/ContentView+ViewBuilders.swift:414-485`). The split
view also still applies a title, subtitle, toolbar, and inspector plumbing at
the shell level (`fichero/fichero/Views/Shell/ContentView/ContentView.swift:340-366`,
`470-489`; `fichero/fichero/Views/Shell/ContentView/ContentView+State.swift:18-77`,
`79-110`). In other words, the current compact path still renders Mac-oriented
shell chrome instead of a phone-specific one-surface flow.

For library and search on compact width, `centerContent` adds a third
navigation layer: `compactLibraryReaderStack`
(`fichero/fichero/Views/Shell/ContentView/ContentView+ViewBuilders.swift:294-305`). That stack is
its own `NavigationStack`, with the list as the root and `previewView` pushed
via `.navigationDestination(item:)`
(`fichero/fichero/Views/Shell/ContentView/ContentView+ViewBuilders.swift:534-566`). The source
comment there explicitly says full edge-swipe stage-to-stage paging is deferred,
so the current implementation is a pushed reader, not an in-view swipe pager
(`fichero/fichero/Views/Shell/ContentView/ContentView+ViewBuilders.swift:551-555`).

On iPad regular width, the sidebar and inspector remain pinned columns. Compact
navigation is only enabled when `horizontalSizeClass == .compact`
(`fichero/fichero/Views/Shell/ContentView/ContentView+State.swift:315-320`), and the sidebar
column is only treated as collapsible in compact mode
(`fichero/fichero/Views/Shell/ContentView/ContentView+State.swift:345-351`). The inspector
defaults to `.docked` outside compact width, and the runtime presenter maps both
`.docked` and `.floating` requests back to a docked inspector presentation
(`fichero/fichero/Views/Inspector/InspectorPresenter.swift:48-69`,
`145-163`). I also verified the current SwiftUI sources do not apply a
`.navigationSplitViewStyle(...)` override anywhere under `fichero/fichero/`,
so the shipped iPad layout is the default pinned-column split behavior.

## Target Model (Planned)

The target interaction model belongs to EPIC `#2810` and child issues
`#2811-#2815`. It is not implemented in the current Swift sources above.

Planned iPhone model:

- A single `NavigationStack` for list -> preview -> reader.
- Reader progression handled in-view with swipe paging, instead of the current
  nested pushed-reader stack.

Planned iPad model:

- Sidebar and inspector move to slide-over presentations instead of always-on
  pinned columns.

Until that work lands, the shipped implementation remains the wrapped
`NavigationSplitView` plus nested compact reader stack described in
"Current Architecture."

## What Already Adapts Correctly

The inspector presenter already has compact-aware behavior. Its placement logic
chooses `.sheet` on compact width and `.docked` otherwise
(`fichero/fichero/Views/Inspector/InspectorPresenter.swift:48-58`), and the
runtime modifier turns compact inspector presentation into either a sheet or a
navigation push rather than forcing a docked column
(`fichero/fichero/Views/Inspector/InspectorPresenter.swift:60-69`,
`145-163`).

`preferredCompactColumn` already points compact collapse at the detail side of
the split. `ContentView.defaultPreferredCompactColumn` is `.detail`, and the
stateful split binding uses that default
(`fichero/fichero/Views/Shell/ContentView/ContentView.swift:31-35`, `93`, `461-465`).

The iOS pairing and capture flows already use mobile-native presentation
patterns instead of Mac window chrome. `FicheroSharedPlatformRoot` presents
incoming pairing links as a sheet, `PairingIncomingLinkSheet` uses a
`NavigationStack`, and `RemoteConnectionSetupView` uses sheets plus a
full-screen document scanner for capture
(`fichero/fichero/FicheroApp_iOS.swift:129-140`, `165-227`, `244-272`,
`276-373`). Inside the main library workspace, `LibraryWorkspaceRoot` also
surfaces capture through iOS-only toolbar actions, sheets, and a
`fullScreenCover`
(`fichero/fichero/Views/Library/LibraryWorkspaceRoot.swift:105-181`).

`LibraryWindow` is correctly macOS-only today. The type is fenced behind
`#if os(macOS)` and owns the AppKit window accessor, file importer, scene-value
menu wiring, and empty navigation title/subtitle that keep Mac window chrome
separate from the iPhone/iPad entry path
(`fichero/fichero/App/LibraryWindow.swift:1-14`, `78-107`).
