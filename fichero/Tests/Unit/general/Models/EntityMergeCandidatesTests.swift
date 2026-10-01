@testable import Fichero
import FicheroAPIClient
import Testing

/// #5129 (maintainer, 2026-09-27): a table Merge asks which entity survives. The sheet proposes the
/// one carrying the most claims, and offers every selected entity. What breaks without these: a
/// proposal that is not the richest row, a tie that reorders the person's selection, or an entity
/// with no id reaching the merge (the engine cannot absorb it).
@Suite("Merge from the entities table proposes a survivor (#5129)")
struct EntityMergeCandidatesTests {
    private func entity(_ id: String?) -> Components.Schemas.KnowledgeEntity {
        Components.Schemas.KnowledgeEntity(id: id, canonicalName: id ?? "unnamed")
    }

    @Test("the entity with the most claims is proposed first")
    func richestFirst() {
        let ranked = mergeCandidatesRichestFirst(
            [entity("a"), entity("b"), entity("c")],
            claimCounts: ["a": 1, "b": 7, "c": 3]
        )
        #expect(ranked.compactMap(\.id) == ["b", "c", "a"])
    }

    @Test("a tie keeps the selection's order; an entity without an id is left out")
    func tiesAndMissingIds() {
        let ranked = mergeCandidatesRichestFirst(
            [entity("x"), entity(nil), entity("y"), entity("z")],
            claimCounts: ["z": 2]
        )
        #expect(ranked.compactMap(\.id) == ["z", "x", "y"])
        #expect(ranked.count == 3)
    }
}
