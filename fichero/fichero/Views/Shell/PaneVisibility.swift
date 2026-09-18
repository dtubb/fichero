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
/// (#1696). This does **not** own the state: the per-window storage stays as the
/// three `@SceneStorage` bools on `ContentView`, so each window keeps its own
/// pane layout.
///
/// It did NOT survive relaunch, though this comment claimed it did until
/// 2026-09-04 — and a comment asserting the very thing that was not happening
/// is a good part of why the bug lived so long. Scene state is restored by
/// macOS window restoration, which a quit does not guarantee; what carries a
/// layout across launches is `WorkspaceLayoutDefaults`, which seeds these
/// bools from the last deliberate choice.
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

// MARK: - ContentView bridge (@SceneStorage ↔ invariant)

extension ContentView {
    /// The current pane visibility, DERIVED from the applied `PaneList` (#4687, spec
    /// workspaces.one-system) — the ONE source of truth, not the legacy `@SceneStorage`
    /// Bools. `applyWorkspaceLayout`, pane close and kind-switch all mutate `activePaneList`
    /// directly and used to leave the three Bools (and everything reading them — toolbar
    /// labels, View-menu checkmarks, `WorkspaceLayoutDefaults.remember`) lying about what was
    /// actually on screen; deriving here instead of reading a mirror makes that impossible.
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
    /// which refuses a change that would empty the window), then mirrors the freshly-DERIVED
    /// visibility onto the legacy `@SceneStorage` Bools so the handful of sites outside this
    /// change's scope that still read them directly (pane-focus cycling, min-width, the
    /// forced-widescreen recovery net — tracked as #4687 follow-up) never drift from what
    /// `paneVisibility` now authoritatively says. Every site — View menu, toolbar, pane close
    /// buttons — routes through this instead of flipping a bool directly.
    func setPaneVisible(_ pane: ContentPane, _ visible: Bool) {
        // With a workspace always applied, the applied `PaneList` is what renders — so a
        // show/hide toggle must mutate IT, or it does nothing (the bug the seed would otherwise
        // introduce). One choke point covers every toggle site (spec workspaces.one-system).
        let nextList = activePaneList.settingVisible(pane.paneKind, visible)
        guard nextList != activePaneList else { return }
        activePaneList = nextList
        syncLegacyPaneVisibilityBools()
        // …and remember the legacy Bool-visibility SHAPE too (Daniel, 2026-09-04: "panes reset
        // each time") — `chat` isn't part of `PaneList`, so it needs this separate remember call
        // alongside the funnel's PaneList one above.
        WorkspaceLayoutDefaults.remember(paneVisibility, chat: showChatPane)
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

    /// Mirror the DERIVED `paneVisibility` onto the legacy `@SceneStorage` Bools (#4687), and
    /// remember the applied `PaneList` for the next launch (#4686). EVERY writer of
    /// `activePaneList` — `setPaneVisible`, `applyWorkspaceLayout`, a saved-workspace apply,
    /// `splitFocusedLeaf`, pane-head close/kind-switch — ends by calling this ONE function, so
    /// there is exactly one place that keeps the Bools and the remembered launch state honest;
    /// a new writer that skips it is the bug class this funnel exists to close off.
    func syncLegacyPaneVisibilityBools() {
        let visibility = paneVisibility
        if visibility.grid != showDocumentGrid { showDocumentGrid = visibility.grid }
        if visibility.canvas != showDocumentCanvas { showDocumentCanvas = visibility.canvas }
        if visibility.reading != showReadingPane { showReadingPane = visibility.reading }
        // Every writer of `activePaneList` calls this ONE function, so it's also the ONE place
        // to remember the composition for the next launch (#4686) — a single write site instead
        // of one per call site.
        WorkspaceLayoutDefaults.rememberPaneList(activePaneList)
    }
}
