import Foundation

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
func sidebarDropOutcomeMessage(
    applied: Int, failed: Int, skips: SidebarDropSkipSummary
) -> String? {
    guard failed > 0 || skips.total > 0 else { return nil }
    var reasons: [String] = []
    if skips.crossSection > 0 {
        reasons.append("\(skips.crossSection) in a different section")
    }
    if skips.selfDrop > 0 {
        reasons.append("\(skips.selfDrop) dropped onto itself")
    }
    if skips.circular > 0 {
        reasons.append("\(skips.circular) would nest a folder inside itself")
    }
    if failed > 0 {
        reasons.append("\(failed) failed")
    }
    let detail = reasons.joined(separator: ", ")
    let total = applied + failed + skips.total
    if applied == 0 {
        let noun = total == 1 ? "item" : "items"
        return "Nothing was dropped (\(total) \(noun): \(detail))."
    }
    return "Dropped \(applied) of \(total) items (\(detail))."
}
