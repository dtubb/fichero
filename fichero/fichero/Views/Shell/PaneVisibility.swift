import SwiftUI

/// The three middle content panes (#1696). Named `ContentPane` (not `Pane` —
/// that's taken by `DocumentKGSurface.Pane`).
enum ContentPane: CaseIterable {
    case grid, canvas, reading
}

/// Visibility of the three middle content panes as ONE value, so the
/// "at least one pane visible" invariant lives in a single, unit-testable place
/// (#1696). This does **not** own the state: the per-window storage stays as the
/// three `@SceneStorage` bools on `ContentView`, so each window still remembers
/// its own pane layout across relaunch (Option A — no persistence regression).
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
    /// The current pane visibility, read from the per-window `@SceneStorage`.
    var paneVisibility: PaneVisibility {
        PaneVisibility(
            grid: showDocumentGrid,
            canvas: showDocumentCanvas,
            reading: showReadingPane
        )
    }

    /// The ONE mutation path for content-pane visibility (#1696): enforces the
    /// "≥1 pane visible" invariant, then writes the result back to the per-window
    /// `@SceneStorage`. Every site — View menu, toolbar, pane close buttons —
    /// routes through this instead of flipping a bool directly, so the invariant
    /// holds everywhere. Writes only the bools that actually change (no
    /// wholesale re-render).
    func setPaneVisible(_ pane: ContentPane, _ visible: Bool) {
        let next = paneVisibility.settingVisible(pane, visible)
        if next.grid != showDocumentGrid { showDocumentGrid = next.grid }
        if next.canvas != showDocumentCanvas { showDocumentCanvas = next.canvas }
        if next.reading != showReadingPane { showReadingPane = next.reading }
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
}
