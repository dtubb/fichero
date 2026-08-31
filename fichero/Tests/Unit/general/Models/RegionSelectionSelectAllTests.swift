@testable import Fichero
import Testing

/// ⌘A over the preview (Daniel, 2026-08-31: all text with the text tool, all
/// boxes with the select tool) lands in the shared holder as ONE replacement,
/// not N accumulating toggles. The three properties the canvas relies on:
/// the set replaces whatever was held, it retargets the artifact the way the
/// single-click path does, and it keeps the caller's order (reading order for
/// a geometry — combine reads it).
@MainActor
struct RegionSelectionSelectAllTests {

    @Test("select-all replaces the whole selection, keeping the given order")
    func replacesAndKeepsOrder() {
        let selection = RegionSelection()
        selection.toggle(9, artifactId: "a", documentId: "d")
        selection.selectAll([2, 0, 1], artifactId: "a", documentId: "d")
        // Given order, NOT sorted and NOT appended to the earlier pick.
        #expect(selection.indices == [2, 0, 1])
        #expect(selection.artifactId == "a")
        #expect(selection.documentId == "d")
        #expect(selection.count == 3)
        #expect(!selection.isEmpty)
    }

    @Test("select-all in another artifact abandons the old selection")
    func retargetsAcrossArtifacts() {
        let selection = RegionSelection()
        selection.selectAll([0, 1, 2], artifactId: "a", documentId: "d")
        selection.selectAll([4], artifactId: "b", documentId: "d2")
        #expect(selection.artifactId == "b")
        #expect(selection.documentId == "d2")
        #expect(selection.indices == [4])
        // Two geometries' indices share no frame — nothing survives from "a".
        #expect(!selection.isSelected(0, in: "a"))
        #expect(selection.isSelected(4, in: "b"))
    }

    @Test("an empty select-all clears rather than leaving stale boxes lit")
    func emptySetClearsIndices() {
        let selection = RegionSelection()
        selection.selectAll([1, 2], artifactId: "a", documentId: "d")
        selection.selectAll([], artifactId: "a", documentId: "d")
        #expect(selection.indices.isEmpty)
        #expect(selection.isEmpty)
        // Same-artifact select-all keeps the target — only `clear()` drops it.
        #expect(selection.artifactId == "a")
    }

    @Test("a nil documentId leaves the last known document in place")
    func nilDocumentIdIsNotDestructive() {
        let selection = RegionSelection()
        selection.selectAll([0], artifactId: "a", documentId: "d")
        selection.selectAll([0, 1], artifactId: "a", documentId: nil)
        #expect(selection.documentId == "d")
        #expect(selection.indices == [0, 1])
    }
}
