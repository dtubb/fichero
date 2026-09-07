@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The entities library view renders an entity as name · type · #claims ·
/// authority link. `EntityTableRow` is the pure mapping behind those columns.
struct EntityTableRowTests {

    private func entity(
        name: String = "Adolfo Hurtado",
        type: Components.Schemas.EntityType_Output? = .person
    ) -> Components.Schemas.KnowledgeEntity {
        Components.Schemas.KnowledgeEntity(id: "e-1", canonicalName: name, entityType: type)
    }

    @Test("name, type and claim count map through")
    func basics() {
        let row = EntityTableRow(entity(), claimCount: 7)
        #expect(row.name == "Adolfo Hurtado")
        #expect(row.type == "Person")
        #expect(row.claimCount == 7)
    }

    @Test("a missing type is empty, not a fabricated label")
    func missingType() {
        #expect(EntityTableRow(entity(type: nil), claimCount: 0).type == "")
    }

    // MARK: - Authority label (the parse that reads metadata["authority_links"])

    @Test("no authority links → empty, never '0 links'")
    func noAuthority() {
        #expect(EntityTableRow.authorityLabel(fromLinks: nil) == "")
        #expect(EntityTableRow.authorityLabel(fromLinks: []) == "")
    }

    @Test("one link renders authority · id")
    func oneLink() {
        let links: [Any] = [["authority": "wikidata", "authority_id": "Q42"]]
        #expect(EntityTableRow.authorityLabel(fromLinks: links) == "WIKIDATA · Q42")
    }

    @Test("multiple links show the first plus a count")
    func manyLinks() {
        let links: [Any] = [
            ["authority": "wikidata", "authority_id": "Q42"],
            ["authority": "viaf", "authority_id": "12345"]
        ]
        #expect(EntityTableRow.authorityLabel(fromLinks: links) == "WIKIDATA · Q42 +1")
    }

    @Test("a link in an unexpected shape still reports that it IS linked")
    func opaqueLink() {
        #expect(EntityTableRow.authorityLabel(fromLinks: ["something"]) == "Linked")
        #expect(EntityTableRow.authorityLabel(fromLinks: ["a", "b"]) == "2 links")
    }

    // MARK: - Curation (the honesty layer)

    @Test("curation state maps to the display badge — verified is Blessed")
    func curationMapping() {
        #expect(EntityTableRow.curation(.verified) == .blessed)
        #expect(EntityTableRow.curation(.rejected) == .rejected)
        #expect(EntityTableRow.curation(.merged) == .merged)
        #expect(EntityTableRow.curation(.unreviewed) == .unreviewed)
        #expect(EntityTableRow.curation(nil) == .unreviewed)
    }
}
