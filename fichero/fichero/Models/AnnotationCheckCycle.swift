import Foundation

/// The reading "check" gesture as a pure rule (spec reading-markup-annotations markup.check.cycle):
/// checking a line cycles ✓ → ✓✓ → ✓✓✓ → clear. Extracted from the two interaction sites
/// (ZoomableImagePreviewMac+Annotations, RegionInteractionLayer) so the progression is ONE testable
/// source of truth — Daniel, 2026-08-30: "a rating is a Check, not a star; three ticks then it's gone."
enum AnnotationCheckCycle {
    /// The next rating for a checked line, or `nil` to CLEAR (delete) the mark.
    ///   nil (no mark yet) → 1 → 2 → 3 → nil
    /// Any rating already at or past ✓✓✓ (3) clears on the next check.
    static func next(_ current: Int?) -> Int? {
        guard let current else { return 1 }   // first check places ✓
        let bumped = current + 1
        return bumped <= 3 ? bumped : nil      // past ✓✓✓ → clear
    }
}
