import Foundation

// MARK: - When a selection change may move the viewport (2026-09-02)

/// Whether a change to `selection` should scroll the list to the primary row.
///
/// The list's `onChange(of: selection)` watcher exists for ONE case (#929): a
/// selection written from somewhere else — the PDF preview scrolling to a new
/// page, a restored launch selection — where the newly-selected row may be off
/// screen and the user has no way to know. It was firing for EVERY selection
/// change, which produced the two defects Daniel reported on 2026-09-02:
///
/// · **Deselect scrolls.** ⌥⇧-clicking row 19 out of a selection left rows 1–18
///   selected, so the "primary" became row 7 and the viewport animated up to
///   it. Removing something from a selection must never move the page you are
///   looking at.
/// · **Every click pays for a scroll.** A plain click animated `scrollTo` on a
///   row that is, by definition, already visible — the user just clicked it.
///   In a `LazyVStack` that forces a layout pass plus a 0.15s animation before
///   the click feels done ("selecting anything takes longer than it should").
///
/// Arrow-key navigation is unaffected: it writes `listScrollTarget`
/// explicitly (`LibraryView+ArrowNavigation`), which is a separate watcher, so
/// declining here costs the keyboard nothing.
///
/// `nonisolated` and free of view state on purpose — it is a rule, and rules
/// are testable off-main (#4201).
enum ListSelectionScrollPolicy {
    /// - Parameters:
    ///   - isUserDriven: the change was made by a live click/keypress in this
    ///     pane (`LibraryView.selectionChangeIsUserDriven`). The row the user
    ///     just acted on is already under their pointer.
    ///   - previous: the selection before the change.
    ///   - next: the selection after it.
    ///   - primary: the row the viewport would move to, in visual order.
    static func shouldScroll(
        isUserDriven: Bool,
        previous: Set<String>,
        next: Set<String>,
        primary: String?
    ) -> Bool {
        // Nothing to scroll to.
        guard let primary else { return false }
        // The user acted here: whatever they touched is on screen already.
        if isUserDriven { return false }
        // A pure narrowing is a DESELECTION — never a reason to move
        // (Daniel: "deselect item 19 and the view jumps to item 7").
        if next.isSubset(of: previous) { return false }
        // The primary row was already selected before this change, so it is
        // where the user has been looking; the change added rows elsewhere.
        if previous.contains(primary) { return false }
        return true
    }
}
