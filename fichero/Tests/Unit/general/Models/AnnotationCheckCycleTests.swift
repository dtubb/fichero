@testable import Fichero
import Foundation
import Testing

/// spec: reading-markup-annotations markup.check.cycle — the reading "check" gesture cycles
/// ✓ → ✓✓ → ✓✓✓ → clear. This pins the ONE pure progression both interaction sites now use
/// (ZoomableImagePreviewMac+Annotations, RegionInteractionLayer).
struct AnnotationCheckCycleTests {

    @Test("the check cycle is nil → 1 → 2 → 3 → clear")
    func fullCycle() {
        #expect(AnnotationCheckCycle.next(nil) == 1)   // first check places ✓
        #expect(AnnotationCheckCycle.next(1) == 2)     // ✓ → ✓✓
        #expect(AnnotationCheckCycle.next(2) == 3)     // ✓✓ → ✓✓✓
        #expect(AnnotationCheckCycle.next(3) == nil)   // ✓✓✓ → clear
    }

    @Test("a rating already past ✓✓✓ clears on the next check")
    func aboveThreeClears() {
        // The model allows 1–5, but the check gesture only reaches ✓✓✓; anything at or beyond clears,
        // so a check can never strand a line at an unreachable 4/5.
        #expect(AnnotationCheckCycle.next(4) == nil)
        #expect(AnnotationCheckCycle.next(5) == nil)
    }

    @Test("checking always advances by one until it clears — never resets to 1 mid-cycle")
    func monotonicUntilClear() {
        // Walk the cycle from a fresh line and assert it visits 1, 2, 3 then clears — the property the
        // two interaction sites rely on (a re-check must never silently drop back to ✓).
        var rating = AnnotationCheckCycle.next(nil)
        #expect(rating == 1)
        var seen: [Int] = []
        while let current = rating {
            seen.append(current)
            rating = AnnotationCheckCycle.next(current)
            #expect(seen.count <= 3, "the cycle must terminate at ✓✓✓, not loop")
        }
        #expect(seen == [1, 2, 3])
    }
}
