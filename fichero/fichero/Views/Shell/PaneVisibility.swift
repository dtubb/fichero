import SwiftUI

/// The three middle content panes (#1696). Named `ContentPane` (not `Pane` —
/// that's taken by `DocumentKGSurface.Pane`).
enum ContentPane: CaseIterable {
    case grid, canvas, reading

    /// The `PaneList` kind this legacy visibility pane maps to, so a show/hide toggle can mutate
    /// the applied workspace (spec workspaces.one-system). `grid` is the library; `canvas` is the
    /// preview/page.
    var paneKind: PaneKind {
        switch self {
        case .grid: .library
        case .canvas: .preview
        case .reading: .reading
        }
    }
}

/// Visibility of the three middle content panes as ONE value, so the
/// "at least one pane visible" invariant lives in a single, unit-testable place
/// (#1696). This owns NO storage of its own (#4687): it is a pure PROJECTION of
/// `ContentView.activePaneList.kinds` (see the `paneVisibility` computed
/// property below) — there is no separate Bool per pane to seed, sync, or drift
/// out of agreement with the applied `PaneList`. `WorkspaceLayoutDefaults`
/// remembers the `PaneList` itself across launches now, not this shape.
struct PaneVisibility: Equatable {
    var grid: Bool
    var canvas: Bool
    var reading: Bool

    func visible(_ pane: ContentPane) -> Bool {
        switch pane {
        case .grid: grid
        case .canvas: canvas
        case .reading: reading
        }
    }

    /// True if any content pane is showing. The invariant keeps this always true
    /// once mutations go through `settingVisible`.
    var isAnyVisible: Bool { grid || canvas || reading }

    /// A copy with `pane` set to `visible`, **enforcing the invariant** that at
    /// least one pane stays visible. Hiding the last visible pane is refused (the
    /// copy is returned unchanged) so the content area is never empty — the
    /// #1696 fix for the pane close buttons / View-menu toggles that used to flip
    /// the bool directly and could leave zero panes.
    func settingVisible(_ pane: ContentPane, _ visible: Bool) -> PaneVisibility {
        var copy = self
        switch pane {
        case .grid: copy.grid = visible
        case .canvas: copy.canvas = visible
        case .reading: copy.reading = visible
        }
        // Never all-hidden: if this change empties the content area, refuse it.
        guard copy.isAnyVisible else { return self }
        return copy
    }
}

// MARK: - ContentView bridge (activePaneList → the invariant type)

extension ContentView {
    /// The current pane visibility, DERIVED from the applied `PaneList` (#4687, spec
    /// workspaces.one-system) — the ONE source of truth. `applyWorkspaceLayout`, pane close and
    /// kind-switch all mutate `activePaneList` directly; every reader of "is the library/preview/
    /// reading pane showing" asks THIS (or `activePaneList` itself), so there is no separate
    /// storage that could disagree with what's actually on screen.
    var paneVisibility: PaneVisibility {
        let kinds = activePaneList.kinds
        return PaneVisibility(
            grid: kinds.contains(.library),
            canvas: kinds.contains(.preview),
            reading: kinds.contains(.reading)
        )
    }

    /// The ONE mutation path for content-pane visibility (#1696): mutates the applied
    /// `PaneList` (enforcing the "≥1 pane visible" invariant via `PaneList.settingVisible`,
    /// which refuses a change that would empty the window), then calls the funnel that persists
    /// it. Every site — View menu, toolbar, pane close buttons — routes through this instead of
    /// flipping a bool directly.
    func setPaneVisible(_ pane: ContentPane, _ visible: Bool) {
        // With a workspace always applied, the applied `PaneList` is what renders — so a
        // show/hide toggle must mutate IT, or it does nothing (the bug the seed would otherwise
        // introduce). One choke point covers every toggle site (spec workspaces.one-system).
        let nextList = activePaneList.settingVisible(pane.paneKind, visible)
        guard nextList != activePaneList else { return }
        activePaneList = nextList
        paneListDidChange()
        // …and remember chat's visibility too (Daniel, 2026-09-04: "panes reset each time") —
        // chat isn't part of `PaneList`, so it needs this separate remember call alongside the
        // funnel's PaneList one above.
        WorkspaceLayoutDefaults.remember(chat: showChatPane)
    }

    /// A `Bool` binding for `pane` whose setter routes through the invariant —
    /// published via `focusedSceneValue` so the View menu (and any toolbar
    /// binding) mutate through the single source of truth.
    func paneBinding(_ pane: ContentPane) -> Binding<Bool> {
        Binding(
            get: { paneVisibility.visible(pane) },
            set: { setPaneVisible(pane, $0) }
        )
    }

    /// Remember the applied `PaneList` for the next launch (#4686). EVERY writer of
    /// `activePaneList` — `setPaneVisible`, `applyWorkspaceLayout`, a saved-workspace apply,
    /// `splitFocusedLeaf`, pane-head close/kind-switch — ends by calling this ONE function, so
    /// there is exactly one place that keeps the remembered launch state honest; a new writer
    /// that skips it is the bug class this funnel exists to close off. Named for what it does
    /// NOW (#4687 deleted the Bool-sync half this used to also do — `paneVisibility` has no
    /// separate storage left to sync).
    func paneListDidChange() {
        WorkspaceLayoutDefaults.rememberPaneList(activePaneList)
    }
}
