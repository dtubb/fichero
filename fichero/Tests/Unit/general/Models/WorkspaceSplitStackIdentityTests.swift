@testable import Fichero
import Foundation
import Testing

/// source-model panes recon, slice C (#4972, 2026-09-20): sizes keyed by PANE ID, not array
/// position, renormalised so survivors grow into a closed peer's freed space. A new suite file
/// (not `WorkspaceSplitStackSizingTests.swift`) per team-lead: keep new cases out of an
/// already-large file rather than growing one further.
struct WorkspaceSplitStackIdentityTests {

    // MARK: - JSON round-trip (pure encode/decode, no @SceneStorage needed)

    @Test("stored fractions round-trip through JSON exactly")
    func storedFractionsRoundTripThroughJSON() throws {
        let paneA = UUID()
        let paneB = UUID()
        let fractions: [UUID: Double] = [paneA: 0.4, paneB: 0.6]
        let json = WorkspaceSplitStack.encodeStoredFractions(fractions)
        let decoded = WorkspaceSplitStack.decodeStoredFractions(try #require(json))
        #expect(decoded == fractions)
    }

    @Test("decoding an empty or malformed JSON string yields an empty map, never a crash")
    func decodingMalformedJSONYieldsEmptyMap() {
        #expect(WorkspaceSplitStack.decodeStoredFractions("").isEmpty)
        #expect(WorkspaceSplitStack.decodeStoredFractions("{}").isEmpty)
        #expect(WorkspaceSplitStack.decodeStoredFractions("not json").isEmpty)
    }

    @Test("decoding ignores a key that isn't a UUID — an unknown id ignored, not crashed on")
    func decodingIgnoresNonUUIDKeys() {
        let decoded = WorkspaceSplitStack.decodeStoredFractions(#"{"not-a-uuid": 0.5}"#)
        #expect(decoded.isEmpty)
    }

    // MARK: - Renormalization (#4972's own fix: survivors grow into freed space)

    @Test("no stored values leaves the array unchanged (every child falls back to its own default)")
    func noStoredValuesIsUnchanged() {
        let defaults: [Double?] = [0.3, 0.7]
        let stored: [Double?] = [nil, nil]
        let result = WorkspaceSplitStack.renormalizedFractions(defaults: defaults, stored: stored)
        #expect(result == [nil, nil])
    }

    /// THE key case: two `.fraction` peers each hold a stored (dragged) value; the FIRST one's
    /// sibling closes (so it is now the ONLY `.fraction` child — `defaults`/`stored` each have
    /// one entry). Its normalized fraction must equal its OWN default share, not its old
    /// (now-meaningless, since its sibling is gone) stored proportion relative to a sibling
    /// that no longer exists.
    @Test("a survivor whose sibling closed grows to its own default share, not its stale stored fraction")
    func survivorGrowsToItsOwnDefaultShareAfterASiblingCloses() {
        // Before close: two peers, defaults [0.3, 0.7], user dragged them to [0.5, 0.5].
        // After close: only the survivor remains — defaults [0.3], stored [0.5].
        let defaults: [Double?] = [0.3]
        let stored: [Double?] = [0.5]
        let result = WorkspaceSplitStack.renormalizedFractions(defaults: defaults, stored: stored)
        #expect(result == [0.3], "the lone survivor's normalized share is its OWN default — 100% of what it's now entitled to")
    }

    @Test("two stored peers renormalize to sum to their COLLECTIVE default share, not 1.0 outright")
    func twoStoredPeersRenormalizeToTheirCollectiveDefaultShare() {
        // Two `.fraction` peers with a combined default of 0.5 (the rest is a `.flex` sibling's
        // share, which this function never touches); the user dragged them to a lopsided 0.9/0.1.
        let defaults: [Double?] = [0.2, 0.3]
        let stored: [Double?] = [0.9, 0.1]
        let result = WorkspaceSplitStack.renormalizedFractions(defaults: defaults, stored: stored)
        let expectedSum = 0.5  // 0.2 + 0.3 — the collective share their defaults were entitled to
        let resultSum = (result[0] ?? 0) + (result[1] ?? 0)
        #expect(abs(resultSum - expectedSum) < 0.0001, "renormalized peers must sum to their collective DEFAULT share")
        #expect(abs((result[0] ?? 0) / (result[1] ?? 0) - 9.0) < 0.0001, "the 9:1 dragged RATIO between them survives")
    }

    @Test("a mix of stored and never-dragged children: unset ones keep nil, stored ones renormalize among themselves")
    func mixOfStoredAndUnsetChildren() {
        let defaults: [Double?] = [0.2, 0.3, 0.1]
        let stored: [Double?] = [0.6, nil, 0.4]
        let result = WorkspaceSplitStack.renormalizedFractions(defaults: defaults, stored: stored)
        #expect(result[1] == nil, "the never-dragged child keeps nil — falls back to its OWN default, untouched")
        let storedSum = (result[0] ?? 0) + (result[2] ?? 0)
        let expectedSum = 0.2 + 0.1  // the two STORED children's collective default share
        #expect(abs(storedSum - expectedSum) < 0.0001)
    }

    @Test("mismatched array lengths return the stored array unchanged rather than crashing")
    func mismatchedLengthsReturnsStoredUnchanged() {
        let result = WorkspaceSplitStack.renormalizedFractions(defaults: [0.5], stored: [0.3, 0.7])
        #expect(result == [0.3, 0.7])
    }

    // MARK: - A workspace's default proportions (Browse: 15/60/25, #4966)

    /// What a NEVER-DRAGGED (or reset — an id-keyed store with no entry for these ids resolves
    /// exactly the same way) Browse layout resolves to: the configured 15/60/25, not equal
    /// thirds. Drives `WorkspaceSplitStack.resolvedExtents` with the SAME `Sizing` values
    /// `PaneSpec.childSizings` would derive from Browse's own `PaneConfig`s, and NO stored
    /// overrides — the id-keyed store's own "unknown id" behavior, proven separately above.
    @Test("Browse's never-dragged (or reset) proportions resolve to 15/60/25, not equal thirds")
    func browseDefaultProportionsResolveToFifteenSixtyTwentyFive() {
        let nodes = BuiltInWorkspaceLayout.browse.panes.nodes
        let preferences: [WorkspaceSplitStack.Sizing?] = nodes.map { node in
            guard case let .leaf(_, _, _, config) = node else { return nil }
            return WorkspaceSplitStack.Sizing.preferred(extent: config.paneExtent, fraction: config.paneFraction)
        }
        let sizings = ContentView.childSizings(preferences, fallbackFraction: 0.4)
        // The reader is the PEER with no explicit fraction — it becomes `.flex`, the same "last
        // child fills the remainder" rule every built-in uses; its 25% is a layout-time fact
        // (`resolvedExtents` honestly returns `nil` for `.flex`, never a guessed pixel value —
        // see the existing sizing-tests file's own comment on this), so this test asserts the
        // two EXPLICIT shares and that the third is flex, not a fabricated 250.
        #expect(sizings == [.fraction(0.15), .fraction(0.60), .flex])
        let total = 1000.0
        let resolved = WorkspaceSplitStack.resolvedExtents(sizings, total: total)
        #expect(resolved.count == 3)
        // 15% / 60% of 1000 — the two configured shares resolve exactly.
        #expect(abs((resolved[0] ?? 0) - 150) < 1)
        #expect(abs((resolved[1] ?? 0) - 600) < 1)
        #expect(resolved[2] == nil, "the reader is the flex peer — resolvedExtents leaves it nil, never a guessed value")
    }
}
