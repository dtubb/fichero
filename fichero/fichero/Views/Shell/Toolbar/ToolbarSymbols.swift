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
    /// Ready splits by TRANSPORT (#4391), extending the documented convention
    /// (triangle = warning, circled exclamation = error) to the healthy
    /// states it never covered:
    ///
    /// - Local (app-managed or an external engine on this Mac): a VERTICAL
    ///   bolt. The old horizontal bolt, filled or not, decayed to a tilde in
    ///   a ring at toolbar size — the symbol for "approximately", read live
    ///   as "not connected". The vertical bolt keeps its identity at 13 pt.
    /// - Remote (another machine): radio waves — the data is leaving this Mac,
    ///   and whether work survives a network drop is a different answer.
    ///
    /// Both are `.fill` (an outline glyph reads as inactive on macOS and
    /// ready is the ACTIVE state — the problem glyph is `.fill` for the same
    /// reason) and `EngineStatusToolbarItem` paints them `.green` so colour
    /// carries the meaning too. A glyph only hints; the popover NAMES the
    /// transport in text (`ConnectionPresentation`, #4380's single source).
    static let engineReadyLocal = "bolt.circle.fill"
    static let engineReadyRemote = "antenna.radiowaves.left.and.right.circle.fill"
    static let engineProblem = "exclamationmark.triangle.fill"
    /// Matches `ItemCategory.activity` — the sidebar's Activity glyph — and is
    /// nothing like the filter's three-lines-in-a-circle (#4360).
    static let activityIdle = "waveform.path.ecg"
    static let activityError = "exclamationmark.circle.fill"

    // MARK: Panes & view (trailing/content zone)
    static let libraryPane = "rectangle.leadinghalf.inset.filled"
    static let previewPane = "rectangle.center.inset.filled"
    static let readingPane = "text.book.closed"
    /// Chat pane toggle (2026-08-12): chat is a ROW pane like preview and
    /// reading, so its toggle joins theirs in the pane group.
    /// Sparkles, not a chat bubble (Daniel 2026-08-12): the bubble read as
    /// "chat app"; sparkles says AI.
    static let chatPane = "sparkles"
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
        ("engine ready (local)", engineReadyLocal),
        ("engine ready (remote)", engineReadyRemote),
        ("engine problem", engineProblem),
        ("activity idle", activityIdle),
        ("activity error", activityError),
        ("library pane toggle", libraryPane),
        ("preview pane toggle", previewPane),
        ("reading pane toggle", readingPane),
        ("chat pane toggle", chatPane),
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
