@testable import Fichero
import Testing

/// #3863 — the KG inspector's grouping pipeline moved off the render path into
/// `recomputeGrouped`. These lock the pure derivations it now precomputes, so the
/// selection order and digest format can't silently drift.
@MainActor
struct KGSectionGroupingTests {

    private func item(_ claimId: String, extras: [String] = []) -> GroupedItem {
        GroupedItem(
            claimId: claimId,
            displayName: claimId.uppercased(),
            context: "ctx-\(claimId)",
            aliases: [],
            extraClaims: extras.map {
                GroupedItem.ExtraClaim(
                    claimId: $0,
                    context: "ctx-\($0)",
                    sourceDocumentId: nil,
                    sourcePageLabel: nil,
                    sourceExcerpt: nil
                )
            }
        )
    }

    @Test("orderedClaimIds = each item's primary claim then its extras, in section order")
    func orderedClaimIdsFlattening() {
        let groups: [(EntityKind, [GroupedItem])] = [
            (.other, [item("c1", extras: ["c1b"]), item("c2")]),
            (.other, [item("c3")])
        ]
        #expect(KnowledgeGraphInspectorSection.orderedClaimIds(from: groups) == ["c1", "c1b", "c2", "c3"])
    }

    @Test("orderedClaimIds is empty for no groups")
    func orderedClaimIdsEmpty() {
        #expect(KnowledgeGraphInspectorSection.orderedClaimIds(from: []).isEmpty)
    }

    @Test("digestMarkup bolds the name and joins contexts with '; '")
    func digestMarkupFormat() {
        #expect(
            KnowledgeGraphInspectorSection.digestMarkup(
                displayName: "Ada", contexts: ["invented X", "met Y"]
            ) == "**Ada** invented X; met Y"
        )
    }
}
