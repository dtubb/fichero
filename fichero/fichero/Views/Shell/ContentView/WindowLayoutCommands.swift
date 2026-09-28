import SwiftUI

/// The focused window's workspace verbs, for the menu bar.
///
/// Equatable is LOAD-BEARING (the RunWorkflowOnSelectionKey lesson): a
/// non-Equatable focused value is byte-compared per body pass, always reads
/// as changed, and cascades focus invalidations. #4968: a blanket `{ true }`
/// (the ORIGINAL fix for that churn) went too far — it also froze
/// `canSplitFocusedLeaf` for `@FocusedValue` consumers, since SwiftUI skips
/// republishing a focused value it considers unchanged, so the View menu's
/// Split rows kept whatever enabled state they had the FIRST time a window
/// published one and never saw a real focus change again (#4968's own
/// diagnosis: "likely the menu bar reads a focused value that is not set" —
/// more precisely, one that never gets marked changed). Comparing the two
/// DATA fields that can actually differ keeps the churn-dampening (an
/// unrelated re-render, same two values, still compares equal — no
/// downstream invalidation) while letting a REAL change through (either
/// value flips → not equal → republished, so the menu's enabled state and
/// its "Split WHAT" wording both stay live). The closures are deliberately
/// excluded from the comparison: they are recreated with a new identity on
/// every `windowLayoutCommands` evaluation regardless of whether anything
/// meaningful changed, so comparing them would reintroduce the exact churn
/// the original blanket `true` was added to dampen.
struct WindowLayoutCommands: Equatable {
    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.canSplitFocusedLeaf == rhs.canSplitFocusedLeaf
            && lhs.focusedPaneKindForSplit == rhs.focusedPaneKindForSplit
            && lhs.focusedLibraryLayout == rhs.focusedLibraryLayout
            // The setter closure captures a leaf id. Two Library panes with the same layout
            // would otherwise compare equal and the menu would keep writing to the OLD pane.
            && lhs.focusedLibraryLeafID == rhs.focusedLibraryLeafID
    }

    let saveWorkspace: @MainActor () -> Void
    let applyWorkspace: @MainActor (SavedWindowWorkspace) -> Void
    /// Apply a v2 built-in workspace (the one built-in system) to the focused window — sets its
    /// `activePaneList` (spec workspaces.one-system). This is what ⌘⌥1–5 drives from the menu bar.
    let applyWorkspaceLayout: @MainActor (BuiltInWorkspaceLayout) -> Void
    /// Split the focused window's focused leaf through the `PaneList` model (spec
    /// panes.split.focused-only, #4685) — the menu-bar twin of the toolbar's Split Right/Below.
    let splitFocusedLeaf: @MainActor (SplitAxis) -> Void
    /// Open this library in a new tab of the focused window (#4685: given a menu-bar home
    /// alongside the toolbar's, per the addendum on #4685).
    let newTab: @MainActor () -> Void
    /// Whether the focused window currently has an eligible focused leaf to split.
    let canSplitFocusedLeaf: Bool
    /// #4968: the focused pane's kind, when the window makes it cheaply available — lets a Split
    /// row name its target ("Split Library Right") instead of a bare "Split Right". `nil` when no
    /// pane has focus, matching `canSplitFocusedLeaf == false` in that case.
    let focusedPaneKindForSplit: PaneKind?
    /// #4968: whether a saved workspace matches what this window currently shows — the checkmark
    /// both menus now display identically (previously toolbar-only).
    let isWorkspaceActive: @MainActor (SavedWindowWorkspace) -> Bool
    /// Slice E (#4965): the FOCUSED Library leaf's own explicit `PaneConfig.libraryLayout`, raw
    /// (`"icons"`/`"list"`/`"table"`/…, `ViewDisplayMode(paneLibraryLayout:)`'s vocabulary — the
    /// SAME string `PaneSpec.paneNodeView` already reads to inject `\.paneLibraryLayout`, not a
    /// second one). `nil` when no Library leaf is focused, OR one is focused but has never had an
    /// explicit layout set (follows the window/workspace default) — the View menu cannot tell
    /// those apart from this field alone and doesn't need to: either way it falls back to
    /// `ViewSettings.libraryLayout` for its checkmark.
    let focusedLibraryLayout: String?
    /// WHICH Library leaf `setFocusedLibraryLayout` writes to; part of equality on purpose.
    let focusedLibraryLeafID: UUID?
    /// Slice E (#4965): write a NEW explicit layout to the focused Library leaf — `nil` when no
    /// Library leaf is focused, so the View menu can tell "write here" apart from "act as today"
    /// (team-lead's own wording) without a separate Bool.
    let setFocusedLibraryLayout: (@MainActor (String) -> Void)?
}
