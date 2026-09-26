import SwiftUI

// `Notification.Name.paneSplitCommand`/`.paneSplitApply`, `SplitPaneAxis`, and
// `PaneSplitCoordinator` (+ its `\.paneSplitCoordinator` environment key) are DELETED (step F,
// source-model panes recon, 2026-09-20): every pane reached through `kindContent` is now a
// `PaneModelSplitHook` pass-through (slice A), so nothing ever called `requestSplit`, and
// `ContentView+LayoutChooser.swift` no longer captures/applies `WindowLayoutSnapshot.splits`
// (that field stays `Codable`, decode-only — an old saved workspace still decodes and simply
// never acts on it, per the HARD rule: never delete or rewrite a user's saved state). Confirmed
// via `find_references`-by-grep before deleting: their only OTHER callers were each other and
// this file's own now-deleted legacy split UI.

// MARK: - Environment: split controls (consumed by MiniToolbar)

/// Injected by SplittablePane so MiniToolbar can render the split buttons
/// inside its own bar rather than requiring a separate top bar.
/// Equatable on the VALUE fields (2026-08-24): the closures capture the same
/// pane state, so only the flags/counts distinguish instances — without this
/// every render republished a "new" environment value and invalidated every
/// reader beneath (the same fault class as ImageZoomActions' ×31 republish).
struct SplitAxisActions: Equatable, @unchecked Sendable {
    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.hasVertical == rhs.hasVertical
            && lhs.hasHorizontal == rhs.hasHorizontal
            && lhs.paneCount == rhs.paneCount
            && lhs.verticalCount == rhs.verticalCount
            && lhs.horizontalCount == rhs.horizontalCount
    }

    let hasVertical: Bool
    let hasHorizontal: Bool
    let paneCount: Int
    /// Per-axis counts (2026-08-24, the 2×2 grid): `paneCount` is the max
    /// and cannot gate per-axis menu rows once both axes are live.
    var verticalCount: Int = 1
    var horizontalCount: Int = 1
    let onToggleVertical: () -> Void
    let onToggleHorizontal: () -> Void
    let onCollapseSplit: () -> Void
}

private struct SplitAxisActionsKey: EnvironmentKey {
    static let defaultValue: SplitAxisActions? = nil
}

extension EnvironmentValues {
    var splitAxisActions: SplitAxisActions? {
        get { self[SplitAxisActionsKey.self] }
        set { self[SplitAxisActionsKey.self] = newValue }
    }
}

// MARK: - Environment: secondary pane flag

/// `true` for every pane that is NOT the primary (top-left / first) instance
/// when a SplittablePane is split. Secondary panes MUST NOT register duplicate
/// NSToolbar items — e.g. `.searchable(placement: .toolbar)` crashes the
/// toolbar subsystem when two views in the same window register the same item.
private struct IsSecondarySplitPaneKey: EnvironmentKey {
    static let defaultValue: Bool = false
}

extension EnvironmentValues {
    /// When `true`, the view is a non-primary copy inside a split pane.
    /// Views that contribute NSToolbar items (`.searchable`, custom
    /// `ToolbarItem`s with fixed identifiers) should skip those contributions
    /// to prevent NSToolbar duplicate-identifier crashes.
    var isSecondarySplitPane: Bool {
        get { self[IsSecondarySplitPaneKey.self] }
        set { self[IsSecondarySplitPaneKey.self] = newValue }
    }
}

// MARK: - Toolbar search registration policy (#1447/#2309)

/// Single source of truth for "may this pane register the toolbar search item?".
/// Only the *primary* pane may register `.searchable(placement: .toolbar)`; a
/// secondary split-pane copy registering the same fixed NSToolbar identifier
/// crashes the toolbar subsystem with a duplicate-identifier error. Every
/// mode-specific view that owns the toolbar search slot (LibraryView)
/// gates its `.searchable` and search `.onSubmit` through this predicate so the
/// invariant lives in one testable place instead of being re-inlined per view.
enum ToolbarSearchRegistration {
    static func shouldRegister(isSecondarySplitPane: Bool) -> Bool {
        !isSecondarySplitPane
    }
}

// `SplitPaneState` DELETED (step F, 2026-09-20): it drove `SplittablePane`'s own legacy
// grid/vertical/horizontal split containers, all removed below — see `SplittablePane.body`.

// MARK: - PaneModelSplitHook (ONE-CODE-PATH ruling, 2026-09-20)

/// A pane the ONE-CODE-PATH ruling requires (source-model panes recon,
/// slice A): when a `SplittablePane` is given this, it never splits ITSELF
/// — the pane system (`PaneList`) is live for the leaf that pane wraps, and
/// split/close already have a real, per-leaf owner
/// (`PaneList.splittingLeaf`/`.removingLeaf`, both verified correct). Before
/// this hook existed, `SplittablePane`'s own `content()` closure was
/// captured ONCE per leaf and re-rendered N times by its internal grid/
/// vertical/horizontal containers — every per-leaf seam injected ABOVE that
/// view (`\.paneKindSwitcher`, `\.paneContentKindSwitcher`,
/// `\.paneContentKind`) is set ONCE, for the ONE model leaf, so every
/// rendered copy read the SAME switcher closure and the SAME environment
/// value: changing "one" copy's kind or content-kind changed the one leaf
/// both copies were drawn from (#4967, #4878, #4979 — confirmed by reading
/// `SplittablePane.swift` and `PaneKindSelector.swift`; see the recon doc
/// for the full trace).
///
/// Top-level, not nested in the generic `SplittablePane<Content>`: this
/// hook does not depend on `Content`, and a caller building
/// `widescreenCanvasPane`/`widescreenReadingPane` (which do not know
/// `SplittablePane`'s `Content` type — it's inferred at the call site) would
/// otherwise have no way to name this type in their own signature.
struct PaneModelSplitHook {
    /// Split THIS pane's own leaf along `axis` (the `PaneList` `SplitAxis`,
    /// `.horizontal`/`.vertical` — NOT the same vocabulary as
    /// `SplittablePane`'s OWN `toggleVertical`/`toggleHorizontal`, which
    /// name a SCREEN DIRECTION (vertical divider = side-by-side) rather
    /// than a stack axis. See `splitAxisActions()`'s mapping.
    let split: (SplitAxis) -> Void

    /// The `SplitAxisActions` a pass-through `SplittablePane` publishes into
    /// `\.splitAxisActions` — pulled out of `SplittablePane.body` so the axis
    /// mapping is a plain function, testable without mounting a view.
    /// `hasVertical`/`hasHorizontal` are always `false`: a further split of
    /// THIS pane produces a new SIBLING leaf in the model, rendered as its
    /// own separate `SplittablePane`, never a second copy of this one — so
    /// `PaneHead`'s close button (gated on `hasVertical || hasHorizontal`)
    /// correctly falls through to the real per-leaf close for every pane
    /// reached through this hook.
    func splitAxisActions() -> SplitAxisActions {
        SplitAxisActions(
            hasVertical: false,
            hasHorizontal: false,
            paneCount: 1,
            // The name swap is real, not a typo: `SplittablePane`'s OWN
            // "vertical" means a VERTICAL DIVIDER (panes side by side —
            // `verticalSplitContainer` is an `HStack`), which is `PaneList`'s
            // `.horizontal` AXIS (`WorkspaceSplitStack(axis: .horizontal)` is
            // also an `HStack`, confirmed at `ContentView.paneListRow`). Its
            // "horizontal" means a horizontal divider (stacked, `VStack`) —
            // `PaneList`'s `.vertical` axis. Get this backwards and "Split
            // Vertical" stacks instead of siding.
            onToggleVertical: { split(.horizontal) },
            onToggleHorizontal: { split(.vertical) },
            onCollapseSplit: {}  // never invoked: hasVertical/hasHorizontal are always false
        )
    }
}

// MARK: - SplittablePane

/// Wraps a content pane so the user can independently split it left/right and
/// top/bottom per column.
///
/// **Split controls** surface inside the pane's own `MiniToolbar` via the
/// `splitAxisActions` environment value - no separate bar is added on top.
///
/// **Bounded split counts:**
/// - each axis cycles through 1, 2, and 3 panes
/// - closing any pane collapses the active axis back one step at a time
/// - secondary panes continue to receive `isSecondarySplitPane = true` so
///   toolbar registrations stay unique
///
/// **NSToolbar safety:** the divider lives in the content area and does not
/// extend into the title bar, so toolbar chrome stays intact.
struct SplittablePane<Content: View>: View {
    private let content: () -> Content
    /// The pane's own split/close owner (`PaneList`, via `PaneModelSplitHook`) — see the type's
    /// own doc comment. Optional so `adaptiveSplittablePane`'s compact-width branch (which never
    /// constructs a `SplittablePane` at all) and any future caller with nothing to split through
    /// stay representable; every PRODUCTION caller today (`kindContent`, the one caller of
    /// `adaptiveSplittablePane`) always supplies one — confirmed by grep before this file was
    /// simplified (step F, source-model panes recon, 2026-09-20). `nil` here renders `content()`
    /// alone, with no `\.splitAxisActions` published — the same "nothing to split" state a
    /// compact-width pane already has, so `PaneChromeMenu`'s "+" correctly stays hidden.
    private let modelSplit: PaneModelSplitHook?

    init(
        storageKey: String,
        modelSplit: PaneModelSplitHook? = nil,
        @ViewBuilder content: @escaping () -> Content
    ) {
        // `storageKey` is no longer stored — nothing in this simplified type keys anything by
        // it any more (step F deleted the `@SceneStorage` counts/extents it used to key); kept
        // as an init parameter so every call site (`adaptiveSplittablePane`) needs no change.
        self.modelSplit = modelSplit
        self.content = content
    }

    var body: some View {
        // ONE CODE PATH (2026-09-20 ruling): this leaf is owned by `PaneList` — it never splits
        // ITSELF. The published actions never report a split in progress
        // (`hasVertical`/`hasHorizontal` are always false, `PaneModelSplitHook.splitAxisActions()`),
        // which also makes `PaneHead`'s close button (gated on those two flags: "collapse the
        // split" vs. "close the leaf") correctly fall through to `\.paneCloseAction` (the real
        // per-leaf close) for every pane reached through this hook.
        if let modelSplit {
            content().environment(\.splitAxisActions, modelSplit.splitAxisActions())
        } else {
            content()
        }
    }
}
