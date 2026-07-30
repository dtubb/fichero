import Foundation

/// One glyph per meaning across the shell toolbar and the status island
/// (#4360).
///
/// Every symbol the window toolbar shows is declared in this one table so the
/// uniqueness rule — no two distinct meanings may share a glyph — is a fact a
/// test can hold (`ToolbarSymbolsTests`), not a convention re-discovered
/// whenever a control is added. The defect this guards against is real: the
/// filter control (`line.3.horizontal.decrease.circle`, three shrinking lines
/// in a circle) and the old activity glyph (`list.bullet.circle`, three
/// bulleted lines in a circle) were indistinguishable at toolbar size, which
/// teaches the user that the glyph means nothing.
///
/// Rules encoded here:
/// - **State never changes a control's shape.** A toggle keeps ONE symbol; its
///   on/off state is the native `Toggle` treatment on the toolbar's Liquid
///   Glass, not a glyph swap. (The old library/preview pane toggles both
///   decayed to a bare `rectangle` when hidden — two meanings, one glyph.)
/// - **A meaning that exists elsewhere reuses that surface's glyph.** The
///   activity button opens the same Activity surface the sidebar lists, so it
///   wears the sidebar's `waveform.path.ecg` (`ItemCategory.activity`).
/// - **Errors keep the two conventional containers.** Triangle = the platform
///   "warning, needs attention" (engine connection); circled exclamation =
///   "a task reported an error" (activity). Same semantic family, deliberately
///   distinct containers and tint.
enum ToolbarSymbols {
    // MARK: Navigation (leading zone)
    static let navigateBack = "chevron.backward"
    static let navigateForward = "chevron.forward"

    // MARK: Breadcrumb (principal zone; decoration, not controls)
    static let breadcrumbLibrary = "books.vertical"
    /// Compact chevron so the separator cannot be mistaken for the Forward
    /// button's full-size `chevron.forward` two inches to its left.
    static let breadcrumbSeparator = "chevron.compact.right"

    // MARK: Status island (principal zone)
    static let engineReady = "bolt.horizontal.circle"
    static let engineProblem = "exclamationmark.triangle.fill"
    /// Matches `ItemCategory.activity` — the sidebar's Activity glyph — and is
    /// nothing like the filter's three-lines-in-a-circle (#4360).
    static let activityIdle = "waveform.path.ecg"
    static let activityError = "exclamationmark.circle.fill"

    // MARK: Panes & view (trailing/content zone)
    static let viewMenu = "rectangle.split.3x1"
    static let libraryPane = "rectangle.leadinghalf.inset.filled"
    static let previewPane = "rectangle.center.inset.filled"
    static let readingPane = "text.book.closed"
    static let inspector = "sidebar.right"

    // MARK: Library list controls
    static let sortMenu = "arrow.up.arrow.down"
    static let filter = "line.3.horizontal.decrease.circle"

    // MARK: Shared mini-toolbar chrome (`MiniToolbar` / `PaneFilterBar` hosts)
    static let overflowMenu = "ellipsis.circle"
    static let splitVertical = "rectangle.split.2x1"
    static let splitHorizontal = "rectangle.split.1x2"
    static let findField = "magnifyingglass"
    static let findPrevious = "chevron.up"
    static let findNext = "chevron.down"
    /// Closing a pane/split. Deliberately NOT `xmark.circle.fill`: the circled
    /// fill is the platform's clear-a-text-field affordance (`clearField`).
    static let closePane = "xmark"
    static let clearField = "xmark.circle.fill"
    static let pin = "pin"
    static let runWorkflow = "bolt"

    /// The audit table: every distinct chrome meaning — window toolbar, status
    /// island, and shared mini-toolbar set — and the one glyph it owns.
    /// `ToolbarSymbolsTests` asserts no symbol appears twice.
    static let allByMeaning: [(meaning: String, symbol: String)] = [
        ("navigate back", navigateBack),
        ("navigate forward", navigateForward),
        ("breadcrumb library", breadcrumbLibrary),
        ("breadcrumb separator", breadcrumbSeparator),
        ("engine ready", engineReady),
        ("engine problem", engineProblem),
        ("activity idle", activityIdle),
        ("activity error", activityError),
        ("view menu", viewMenu),
        ("library pane toggle", libraryPane),
        ("preview pane toggle", previewPane),
        ("reading pane toggle", readingPane),
        ("inspector toggle", inspector),
        ("sort menu", sortMenu),
        ("filter toggle", filter),
        ("overflow menu", overflowMenu),
        ("split vertical", splitVertical),
        ("split horizontal", splitHorizontal),
        ("find field", findField),
        ("find previous match", findPrevious),
        ("find next match", findNext),
        ("close pane", closePane),
        ("clear field", clearField),
        ("pin pane", pin),
        ("run workflow", runWorkflow)
    ]
}
