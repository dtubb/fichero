# 13. SwiftUI Standards


### SwiftUI-first, Golden Gate only

Fichero’s frontend is SwiftUI-first, targeting **macOS 26 only** — no back-deployment, no `if #available` guards; adopt current APIs directly. Default to SwiftUI for everything; drop to AppKit only for a documented gap, behind a contained `NSViewRepresentable` / `NSViewControllerRepresentable` bridge (below). Read from services/HTTP — never local file paths; the engine may be remote.

### State management: Observation-first

For ANY new view-model or store:

- `@Observable` (Observation framework) — NOT `ObservableObject` / `@Published` / Combine. The pre-2026 `@StateObject`/`ObservableObject` pattern is obsolete for new code.
- `@State` to own an `@Observable`; `@Bindable` for two-way bindings; `@Environment(Type.self)` for dependency injection. Use lazy `@State` init when construction is costly.
- Migrate existing view-local `ObservableObject` view-models to `@Observable` as you touch each surface, updating consumers from `@StateObject`/`@ObservedObject` to `@State`/`@Bindable`. Exception: the app-wide god objects (`DocumentStore`, `LibraryManager`, `AppState`, and widely-consumed service wrappers) have huge blast radius — migrate them only in a deliberate, dedicated pass.
- Replace `NotificationCenter`-as-mutation-bus with an observed store. Posting notifications to fan mutations across views is the anti-pattern.
- State lives in stores/services injected through the environment; views stay thin, render, and collect input — they never call the API directly. Stores are the only endpoint accessors, and they update one item in place rather than re-rendering whole lists.

Modern SwiftUI to prefer: native `List`/`Section` selection (NSTableView underneath → free macOS selection emphasis and context-menu target ring), `\.appearsActive` / `\.isEmphasized` for focus loss, List/Grid/Section content-reordering APIs, toolbar visibility-priority and auto-minimizing, AsyncImage caching, Liquid Glass / `.regularMaterial` for chrome, SF Symbols for glyphs, and `swift-collections` (`OrderedSet` / `OrderedDictionary`) where ordering/dedup matters.

### Swift 6 concurrency (mandatory)

Strict concurrency checking is on.

- `@MainActor` for UI-related classes; the actor provides serialization — never add dispatch queues inside a `@MainActor` class, and never `DispatchQueue.main.async` anywhere.
- From non-isolated closures, hop with `Task { @MainActor in ... }`.
- Every `.task {}` block checks `Task.isCancelled` — otherwise work keeps running after the view disappears.
- Types that implement their own thread safety (a lock) conform to `@unchecked Sendable`.
- No concurrency warnings in the build.

### File, size, and naming rules

- **File size**: 400 lines recommended limit; 1,000 lines hard limit (requires split). Type bodies \< 250 lines; functions \< 50 lines; cyclomatic complexity \< 10; lines \< 120 characters.
- Split by component (extract sub-views), by responsibility, or by feature.
- **Files**: PascalCase, descriptive (`DocumentRow`, not `Row`), suffixed by purpose where useful (`…View`, `…Model`, `…Service`).
- **Variables**: descriptive camelCase — never `x`, `y`, `i`, `dx`. **Functions**: verb-first (`loadDocument()`, `handleFileDropOnLibrary()`).
- Standard in-file order: imports, logger, properties, body, subviews as `@ViewBuilder` computed properties, actions, helpers, supporting types, preview.
- **OSLog only** — a `Logger(subsystem: "com.tubb.Fichero", category: …)` per file; never `NSLog` or `print`.
- **Semantic system fonts** (`.title`, `.body`) — never `.system(size:)`.
- Cache expensive computations in `@State` and rebuild on `.onChange`; never rebuild hierarchies or create service objects inside `body`.
- Use `@FocusedValue` for menu commands, never `NotificationCenter`.
- SwiftLint is required before committing: `swiftlint lint fichero/fichero/` (auto-fix whitespace with `swiftlint --fix --format`).
- New `.swift` files must be registered: `ruby scripts/add-swift-file.rb <path>` (chapter 10).

### AppKit interop policy

Two sanctioned reasons to bridge, both with the same containment discipline (isolate behind an `NSViewRepresentable`, documented, never AppKit sprinkled through view code):

1.  **Capability gap** — SwiftUI literally cannot do it. The ~8 shipped bridges: PDFKit rendering and zoom, the image magnifier / cursor tracking, scroll-wheel zoom, Quick Look, rich/plain-text editors, and an `NSEvent` swipe monitor.
2.  **Behavioral-fidelity gap** — SwiftUI renders it but cannot match a decades-old Mac interaction a power user feels the absence of: selection emphasis on focus loss, the context-menu target focus ring, drag-session visibility, type-in-search with arrow-through-results, precise toolbar placement across a three-pane split.

A fidelity bridge folds into the existing list/inspector/reading stack — no parallel AppKit inspector. If `List` already gives the behavior, use `List`. Before any new bridge: check current Apple documentation for a native SwiftUI answer first (SwiftUI 2026 closed several old gaps natively), then bridge only a confirmed gap and add it to the sanctioned list. A bridge changes presentation/interaction, never business logic; Swift 6 concurrency rules apply inside it.

Control choice per surface: `List` for single-column item lists (the inspector’s entities/claims/notes/annotations, sidebar nav) — it supports multi-select, hierarchy (`Section`/`OutlineGroup`), and drag-to-reorder; `Table` for multi-column sortable tabular data (the library browser); a bridged `NSOutlineView`/`NSTableView` only if those cannot express a needed combination. **Swipe actions are not Mac-normal** — on macOS, row actions go in the context menu, toolbar, and keyboard, never a swipe. Editing is navigation, not modal: inline `TextField` for rename, or push a detail/edit view inside the inspector with a Back button; confirmations may be alerts, editing never is.

Before declaring SwiftUI work done, the three-leg check in order: `swiftlint` clean, the build succeeds, the tests pass. A build log alone is not done; a green test run alone is not done.
