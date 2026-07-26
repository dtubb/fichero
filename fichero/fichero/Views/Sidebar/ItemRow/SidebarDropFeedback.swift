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

/// User-facing summary for a partially-applied (or fully-rejected) multi-item
/// drop. Returns nil when nothing was skipped — clean drops stay silent.
func sidebarDropSkipMessage(moved: Int, skips: SidebarDropSkipSummary) -> String? {
    guard skips.total > 0 else { return nil }
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
    let reasonList = reasons.joined(separator: ", ")
    if moved == 0 {
        let noun = skips.total == 1 ? "item" : "items"
        return "Nothing was moved (\(skips.total) \(noun) skipped: \(reasonList))."
    }
    let total = moved + skips.total
    return "Moved \(moved) of \(total) items (skipped: \(reasonList))."
}
