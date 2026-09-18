@testable import Fichero
import Testing

/// SF3 review finding: `WorkspaceSplitStack.seedIfNeeded` used to convert a `.fraction` child's
/// share into ABSOLUTE POINTS on first appear and write it into `@SceneStorage` — so a 0.4-fraction
/// column seeded once at a 1000pt window stayed pinned to 400pt forever, even after the window (or
/// the whole Mac) moved to a very different size, because the stored override then always won over
/// the fraction. The fix deletes the eager seed entirely: `resolvedExtents` (below) already treats
/// an absent/unset stored override as "use the fraction of `total`", recomputed fresh every call —
/// PURE, no view mounted, no `@SceneStorage`, matching the `WorkspaceSplitStackSizingTests` idiom.
struct WorkspaceSplitStackSeedingTests {

    @Test("with no stored override (no drag ever happened), a fraction re-resolves proportionally at a different total")
    func fractionStaysProportionalAcrossTotalsWhenUnseeded() {
        // Same sizing, same "no drag yet" storedOverrides ([nil]) — only `total` changes, exactly
        // what happens when the SAME applied workspace's window is resized, or the same built-in
        // is re-applied on a differently-sized display. Before the fix, a real WorkspaceSplitStack
        // would have written an absolute points value into @SceneStorage on the FIRST of these and
        // never revisited it; this test pins the pure function the fix now relies on to keep
        // resolving live instead.
        let laptop = WorkspaceSplitStack.resolvedExtents(
            [.fraction(0.4), .flex], storedOverrides: [nil, nil], total: 1000
        )
        let display = WorkspaceSplitStack.resolvedExtents(
            [.fraction(0.4), .flex], storedOverrides: [nil, nil], total: 2000
        )
        #expect(laptop[0] == 400)
        #expect(display[0] == 800, "an unseeded fraction must track the CURRENT total, not the first one it ever saw")
    }

    @Test("a stored override (an actual drag happened) wins over the fraction regardless of total")
    func aRealDragsStoredValueOverridesTheFraction() {
        // This is the ONE case where a fixed number should persist across a resize — because the
        // user asked for it with a drag, not because seeding minted it silently.
        let resolved = WorkspaceSplitStack.resolvedExtents(
            [.fraction(0.4), .flex], storedOverrides: [555, nil], total: 2000
        )
        #expect(resolved[0] == 555)
    }
}
