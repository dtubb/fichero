import Foundation

/// Is `draggedId` the same item as `targetId`? The one check every drop site
/// asks first — pulled out to a single pure function (#4980) so the sidebar
/// row drop and the Library cell drop share ONE answer to "did this land on
/// itself" instead of each spelling the comparison inline. A self-drop is
/// refused HERE, before any move is attempted, and is never treated as a
/// failure: it was a drag that slipped, not a request (Finder does the same).
func sidebarDropIsSelfTarget(draggedId: String, targetId: String) -> Bool {
    draggedId == targetId
}

/// Per-reason counts for rows a multi-item drop skipped. A drop applies the
/// valid subset and skips the rest; these counts feed the user-facing summary
/// so partial application is never silent (prefer-raise-over-silent-fallback).
struct SidebarDropSkipSummary: Equatable {
    var crossSection = 0
    var selfDrop = 0
    var circular = 0
    var total: Int { crossSection + selfDrop + circular }
}

/// User-facing summary for a multi-item drop built from REAL outcomes —
/// `applied` counts operations that actually completed (moves are optimistic,
/// copies/aliases are awaited), `failed` counts async failures. Returns nil
/// when everything applied cleanly — clean drops stay silent. Wording is
/// operation-neutral ("dropped") because a drop can mix move/copy/alias.
///
/// `selfDrop` skips are deliberately EXCLUDED from what makes this non-nil
/// (#4980): dropping an item onto itself (alone, or as one of several
/// dragged items) is a drag that slipped, not a failed request — Finder
/// stays silent about it, and so must this alert. A folder dropped into its
/// own descendant is different: it IS a real, meaningful refusal, so it
/// still counts (`circular`), same as a cross-section drop.
func sidebarDropOutcomeMessage(
    applied: Int, failed: Int, skips: SidebarDropSkipSummary
) -> String? {
    let reportableSkips = skips.crossSection + skips.circular
    guard failed > 0 || reportableSkips > 0 else { return nil }
    var reasons: [String] = []
    if skips.crossSection > 0 {
        reasons.append("\(skips.crossSection) in a different section")
    }
    if skips.circular > 0 {
        reasons.append("\(skips.circular) would nest a folder inside itself")
    }
    if failed > 0 {
        reasons.append("\(failed) failed")
    }
    let detail = reasons.joined(separator: ", ")
    // Self-drops are counted in `applied`'s denominator so a mixed drag still
    // reports its true item count, but never appear in `detail` above.
    let total = applied + failed + reportableSkips + skips.selfDrop
    if applied == 0 {
        let noun = total == 1 ? "item" : "items"
        return "Nothing was dropped (\(total) \(noun): \(detail))."
    }
    return "Dropped \(applied) of \(total) items (\(detail))."
}
