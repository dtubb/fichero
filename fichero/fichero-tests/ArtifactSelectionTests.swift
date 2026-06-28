@testable import Fichero
import Foundation
import Testing

// Tests for the artifacts-browser multi-select + delete helpers (#2519).
// Covers: delete resolves the FULL selection (not just the focused row),
// stale/empty ids are dropped, and detail-follow focus rules across
// empty / single / multi selection — the behaviours that drive the List.

@Suite("ArtifactSelection — multi-select + delete helpers (#2519)")
struct ArtifactSelectionTests {

    private func artifact(_ id: String, documentId: String = "doc-1") -> Artifact {
        Artifact(id: id, documentId: documentId, sourceArtifactId: nil,
                 version: 1, artifactType: "transcript", content: nil,
                 data: nil, runId: nil, provider: nil, model: nil,
                 stepName: "transcript", confidence: nil,
                 reviewed: false, createdAt: Date())
    }

    private var items: [Artifact] {
        [artifact("a"), artifact("b"), artifact("c")]
    }

    // MARK: - resolve (delete acts on the full selection)

    @Test("resolve returns every selected artifact, in list order")
    func resolveFullSelection() {
        let result = ArtifactSelection.resolve(["c", "a"], in: items)
        #expect(result.map(\.id) == ["a", "c"])  // list order, not set order
    }

    @Test("resolve on an empty selection is empty (regression: no delete-all)")
    func resolveEmpty() {
        #expect(ArtifactSelection.resolve([], in: items).isEmpty)
    }

    @Test("resolve drops ids not present in items (stale / already-deleted)")
    func resolveDropsStale() {
        let result = ArtifactSelection.resolve(["a", "ghost"], in: items)
        #expect(result.map(\.id) == ["a"])
    }

    @Test("resolve against an empty list is empty")
    func resolveEmptyList() {
        #expect(ArtifactSelection.resolve(["a"], in: []).isEmpty)
    }

    // MARK: - focusedID (detail follows a single selection)

    @Test("empty selection clears focus")
    func focusEmpty() {
        #expect(ArtifactSelection.focusedID(for: [], current: "a") == nil)
    }

    @Test("single selection focuses that row")
    func focusSingle() {
        #expect(ArtifactSelection.focusedID(for: ["b"], current: "a") == "b")
    }

    @Test("multi-selection keeps the current focus (no jump during batch delete)")
    func focusMultiKeepsCurrent() {
        #expect(ArtifactSelection.focusedID(for: ["a", "b"], current: "a") == "a")
        // current may be nil while multi-selecting — stays nil, doesn't pick arbitrarily
        #expect(ArtifactSelection.focusedID(for: ["a", "b"], current: nil) == nil)
    }
}
