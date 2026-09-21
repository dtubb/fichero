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

    // MARK: - A stored size is used as it is (#5014, #5012)

    /// Browse's row: Library 0.15, Preview 0.60, Reader flexing. Real pane ids from the built-in.
    private static let browseSizings: [WorkspaceSplitStack.Sizing] = [.fraction(0.15), .fraction(0.60), .flex]
    private static var browseIDs: [UUID] { BuiltInWorkspaceLayout.browse.panes.nodes.map(\.id) }

    @Test("nothing stored: every child falls back to its own default")
    func nothingStoredMeansNoOverrides() {
        let overrides = WorkspaceSplitStack.storedOverrides(
            sizings: Self.browseSizings, ids: Self.browseIDs, storedById: [:], total: 1000
        )
        #expect(overrides == [nil, nil, nil])
    }

    /// #5012: with ONLY the Library dragged, the old per-pass rescale computed (v / v) x default,
    /// which is always the default, so the drag was undone and the divider looked dead.
    @Test("one dragged pane keeps its dragged size; it is not scaled back to its default")
    func aLoneStoredSizeSurvives() {
        let ids = Self.browseIDs
        let overrides = WorkspaceSplitStack.storedOverrides(
            sizings: Self.browseSizings, ids: ids, storedById: [ids[0]: 0.30], total: 1000
        )
        #expect(overrides[0] == 300, "the Library was dragged to 30 percent and stays there")
        #expect(overrides[1] == nil, "the Preview was never dragged")
    }

    /// #5014: with two stored sizes the old rescale pinned their SUM to the sum of their
    /// defaults, so dragging the right-hand divider could only move the left-hand pane.
    @Test("dragging one pane leaves another dragged pane's size alone")
    func twoStoredSizesAreIndependent() {
        let ids = Self.browseIDs
        let before = WorkspaceSplitStack.storedOverrides(
            sizings: Self.browseSizings, ids: ids, storedById: [ids[0]: 0.20, ids[1]: 0.50], total: 1000
        )
        let after = WorkspaceSplitStack.storedOverrides(
            sizings: Self.browseSizings, ids: ids, storedById: [ids[0]: 0.20, ids[1]: 0.40], total: 1000
        )
        #expect(before[0] == 200)
        #expect(after[0] == 200, "the Library did not move when the Preview's divider was dragged")
        #expect(after[1] == 400)
    }

    @Test("a closed pane's stored size is simply never read")
    func aClosedPanesStoredSizeIsIgnored() {
        let ids = Self.browseIDs
        let survivors = [ids[0], ids[2]]
        let overrides = WorkspaceSplitStack.storedOverrides(
            sizings: [.fraction(0.15), .flex], ids: survivors,
            storedById: [ids[0]: 0.20, ids[1]: 0.50], total: 1000
        )
        #expect(overrides == [200, nil], "the survivor keeps its size and the flexing pane takes the freed space")
    }

    @Test("mismatched array lengths give no overrides rather than crashing")
    func mismatchedLengthsGiveNoOverrides() {
        let overrides = WorkspaceSplitStack.storedOverrides(
            sizings: Self.browseSizings, ids: [], storedById: [:], total: 1000
        )
        #expect(overrides == [nil, nil, nil])
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

    // MARK: - Slice D (#4876/#4848, 2026-09-20): a default, not a pin

    /// Every leaf (kind + config) anywhere in a list, splits flattened — same helper shape as
    /// `BuiltInWorkspaceLayoutTests.allLeaves`, kept local since that file wasn't touched here.
    private func allLeaves(_ list: PaneList) -> [(kind: PaneKind, config: PaneConfig)] {
        var out: [(kind: PaneKind, config: PaneConfig)] = []
        func walk(_ node: PaneNode) {
            switch node {
            case let .leaf(_, kind, _, config): out.append((kind: kind, config: config))
            case let .split(_, _, children): children.forEach(walk)
            }
        }
        list.nodes.forEach(walk)
        return out
    }

    /// "Every built-in workspace with a bottom row declares a resizable boundary above it":
    /// proven in two parts, since there is no mounted harness to watch a divider actually draw
    /// (see the file-level note in the slice report). Part one, here: every leaf that pins an
    /// extent (`PaneConfig.paneExtent` — the only field a bottom strip uses) resolves to
    /// `Sizing.fixed`, and `Sizing.fixed` — since slice D — is proven RESIZABLE (not exempt from
    /// a divider) by `resolvedFixedExtentHonoursAStoredOverride` and
    /// `resolvedExtentsHonoursAStoredOverrideForAFixedChild` below: a `.fixed` child that ignored
    /// drag state, as it did before this slice, could never round-trip a stored value the way
    /// those tests prove it now does.
    @Test("every built-in workspace's paneExtent-pinned leaf resolves to Sizing.fixed, the sizing slice D made resizable")
    func everyPaneExtentLeafResolvesToFixedSizing() {
        var foundAtLeastOne = false
        for layout in BuiltInWorkspaceLayout.allCases {
            for leaf in allLeaves(layout.panes) {
                guard let extent = leaf.config.paneExtent else { continue }
                foundAtLeastOne = true
                let sizing = WorkspaceSplitStack.Sizing.preferred(extent: extent, fraction: leaf.config.paneFraction)
                #expect(sizing == .fixed(extent), "\(layout.title)'s pinned leaf must resolve to .fixed")
            }
        }
        #expect(foundAtLeastOne, "expected at least one built-in workspace to have a paneExtent-pinned bottom row")
    }

    /// The default (never-dragged) resolution is exactly today's height — `resolvedFixedExtent`
    /// with `stored: nil` falls straight back to the configured default, unchanged from before
    /// this slice.
    @Test("a fixed child's default (never-dragged) resolution is exactly its configured height")
    func fixedChildDefaultResolutionIsUnchanged() {
        #expect(WorkspaceSplitStack.resolvedFixedExtent(default: 72, stored: nil) == nil)
        // `nil` here means "no override" — `resolvedExtents`'s own fallback (unchanged) is what
        // actually returns the configured default; proven directly below.
        let resolved = WorkspaceSplitStack.resolvedExtents([.fixed(72), .flex], total: 800)
        #expect(resolved[0] == 72)
    }

    /// A drag grows the strip, but can never shrink it below its own configured default.
    @Test("a fixed child's dragged height is floored at its own default — it can grow, never shrink below it")
    func fixedChildDraggedHeightIsFlooredAtItsDefault() {
        #expect(WorkspaceSplitStack.resolvedFixedExtent(default: 72, stored: 150) == 150, "growing past the default is honoured")
        #expect(WorkspaceSplitStack.resolvedFixedExtent(default: 72, stored: 40) == 72, "a stored value below the default is floored, not honoured")
    }

    /// `resolvedExtents` itself honours a stored override for a `.fixed` child (not just the
    /// pure floor helper in isolation) — this is the exact behavior that was MISSING before this
    /// slice (`.fixed` used to ignore `storedOverrides` unconditionally).
    @Test("resolvedExtents honours a stored override for a .fixed child, not just its default")
    func resolvedExtentsHonoursAStoredOverrideForAFixedChild() {
        let resolved = WorkspaceSplitStack.resolvedExtents(
            [.fixed(72), .flex], storedOverrides: [140, nil], total: 800
        )
        #expect(resolved[0] == 140)
    }

    /// "A dragged height persists by id and survives a sibling closing": a `.fixed` child's
    /// stored value is looked up ONLY by its own id (`decodeStoredFractions`, unchanged from
    /// slice C) and never renormalized against a sibling (unlike `.fraction` — `.fixed` values
    /// are independent, absolute points, see `resolvedFixedExtent`'s own doc comment) — so
    /// encoding two strips' drags, then reading back only the SURVIVOR's id after a simulated
    /// close (simply not looking up the closed id — nothing ever prunes an entry), returns the
    /// survivor's value completely unchanged.
    @Test("a fixed child's dragged height persists by id, unaffected by a sibling closing")
    func fixedChildDraggedHeightPersistsByIdAcrossASiblingClose() throws {
        let survivor = UUID()
        let closed = UUID()
        let json = WorkspaceSplitStack.encodeStoredFractions([survivor: 160, closed: 90])
        let decoded = WorkspaceSplitStack.decodeStoredFractions(try #require(json))
        // The "close": the closed pane's id is simply never looked up again.
        let survivorResolved = WorkspaceSplitStack.resolvedFixedExtent(default: 72, stored: decoded[survivor])
        #expect(survivorResolved == 160, "the survivor's own dragged height is exactly what was stored, untouched by the sibling's closing")
    }
}
