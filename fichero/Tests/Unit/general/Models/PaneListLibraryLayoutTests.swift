@testable import Fichero
import Foundation
import Testing

/// source-model panes recon, slice E (#4965, 2026-09-20): the View menu writes the FOCUSED
/// Library pane's own `PaneConfig.libraryLayout`, mirroring `changingLeafContentKind`'s existing
/// per-leaf seam — a new suite file per team-lead (new cases stay out of the oversized ones).
struct PaneListLibraryLayoutTests {

    @Test("changing one Library leaf's layout leaves another Library leaf's layout untouched")
    func changingOneLeafsLayoutLeavesAnotherUntouched() {
        let leafA = UUID()
        let leafB = UUID()
        let list = PaneList([
            .leaf(id: leafA, kind: .library, scope: .current, config: PaneConfig(libraryLayout: "table")),
            .leaf(id: leafB, kind: .library, scope: .current, config: PaneConfig(libraryLayout: "icons"))
        ])

        let after = list.changingLeafLibraryLayout(leafA, to: "list")

        #expect(after.config(for: leafA)?.libraryLayout == "list", "the targeted leaf changed")
        #expect(after.config(for: leafB)?.libraryLayout == "icons", "the OTHER Library leaf is untouched")
    }

    @Test("changing a leaf's layout leaves its other config fields (content kind, scope) untouched")
    func changingLayoutLeavesOtherFieldsUntouched() {
        let leaf = UUID()
        let list = PaneList([
            .leaf(
                id: leaf, kind: .library, scope: .current,
                config: PaneConfig(libraryContentKind: "claims", libraryLayout: "table", paneFraction: 0.3)
            )
        ])

        let after = list.changingLeafLibraryLayout(leaf, to: "icons")

        let config = after.config(for: leaf)
        #expect(config?.libraryLayout == "icons")
        #expect(config?.libraryContentKind == "claims", "content kind untouched")
        #expect(config?.paneFraction == 0.3, "size preference untouched")
    }

    @Test("clearing a leaf's layout (nil) goes back to following the window/workspace default")
    func clearingLayoutGoesBackToNil() {
        let leaf = UUID()
        let list = PaneList([.leaf(id: leaf, kind: .library, scope: .current, config: PaneConfig(libraryLayout: "table"))])
        let after = list.changingLeafLibraryLayout(leaf, to: nil)
        #expect(after.config(for: leaf)?.libraryLayout == nil)
    }

    @Test("changing a layout for an id that isn't present is a no-op")
    func changingLayoutForMissingIdIsNoOp() {
        let list = PaneList([.leaf(.library, config: PaneConfig(libraryLayout: "table"))])
        let after = list.changingLeafLibraryLayout(UUID(), to: "icons")
        #expect(after == list)
    }

    @Test("a leaf's explicit layout round-trips through the saved-workspace JSON")
    func layoutRoundTripsThroughSavedWorkspaceJSON() throws {
        let list = PaneList([.leaf(.library, config: PaneConfig(libraryLayout: "columns"))])
        let data = try JSONEncoder().encode(list)
        let decoded = try JSONDecoder().decode(PaneList.self, from: data)
        #expect(decoded == list)
        guard case let .leaf(_, _, _, config) = decoded.nodes[0] else {
            Issue.record("expected a leaf"); return
        }
        #expect(config.libraryLayout == "columns")
    }

    /// Same discipline as `PaneListTests.oldWorkspaceWithoutContentKindDecodesToNil`: an OLD
    /// saved workspace whose JSON simply never had `libraryLayout` set decodes to `nil` for it —
    /// never a crash, never a guessed default. Simulated honestly: a config that never SET
    /// `libraryLayout` encodes with no key for it at all (`encodeIfPresent` on the synthesized
    /// `Codable`), so this first proves the JSON really is what an old save looks like.
    @Test("an old saved workspace with no libraryLayout key decodes to nil, not a crash or a guessed default")
    func oldWorkspaceWithoutLibraryLayoutKeyDecodesToNil() throws {
        let preExisting = PaneList([.leaf(.library, config: PaneConfig(libraryContentKind: "entities"))])
        let data = try JSONEncoder().encode(preExisting)
        let json = try #require(String(data: data, encoding: .utf8))
        #expect(!json.contains("libraryLayout"), "this JSON is meant to simulate a pre-slice-E save — it must not already carry the key")

        let decoded = try JSONDecoder().decode(PaneList.self, from: data)
        guard case let .leaf(_, _, _, config) = decoded.nodes[0] else {
            Issue.record("expected a leaf"); return
        }
        #expect(config.libraryLayout == nil)
        #expect(config.libraryContentKind == "entities", "the field that WAS there still decodes")
    }

    // MARK: - LibraryLayoutSection's vocabulary conversion (pure, static — no view mount needed)

    @Test("every layout this menu offers converts to a pane-config raw value and back to itself")
    func everyOfferedLayoutRoundTripsThroughTheRawVocabulary() {
        for layout: LibraryLayout in [.icons, .list, .table, .columns, .canvas, .space] {
            let raw = LibraryLayoutSection.paneLayoutRawValue(for: layout)
            #expect(raw != nil, "\(layout) is offered by this menu, so it must have a raw value")
            let roundTripped = raw.flatMap { LibraryLayoutSection.libraryLayout(fromPaneRaw: $0) }
            #expect(roundTripped == layout, "\(layout) must round-trip through its own raw value")
        }
    }

    @Test("a layout the pane-config field doesn't recognize converts to nil, not a guess")
    func unrecognisedLayoutsConvertToNil() {
        for layout: LibraryLayout in [.grid, .cards, .timeline, .calendar, .geoMap] {
            #expect(LibraryLayoutSection.paneLayoutRawValue(for: layout) == nil)
        }
    }

    @Test("an unrecognised raw string converts to nil, not a crash")
    func unrecognisedRawStringConvertsToNil() {
        #expect(LibraryLayoutSection.libraryLayout(fromPaneRaw: "not-a-real-layout") == nil)
    }
}
