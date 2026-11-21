@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// spec: kg-rendering — `kg.render.date-is-never-a-node`,
/// `kg.render.literal-node-tap-is-safe`,
/// `kg.render.an-object-that-is-not-a-name-stays-in-the-sentence` (#6772).
///
/// The engine returns a statement whose object never resolved to a name as an
/// edge to `literal:<object phrase>`. The graph draws names only: no node for a
/// literal, the statement counted on its subject, and a tapped id that is a
/// literal never becomes the focus (its neighbourhood fetch answers 404).
struct GraphSimulationNamesOnlyTests {
    private func response(_ json: String) throws -> Components.Schemas.NeighborhoodResponse {
        try JSONDecoder().decode(Components.Schemas.NeighborhoodResponse.self, from: Data(json.utf8))
    }

    private let neighbourhood = """
    {
      "focus_entity_id": "hindenburg",
      "focus_canonical_name": "Hindenburg",
      "focus_entity_type": "person",
      "neighbors": [
        {"id": "papen", "canonical_name": "Papen", "entity_type": "person", "hop": 1},
        {"id": "literal:1932", "canonical_name": "1932", "hop": 1}
      ],
      "edges": [
        {"source_id": "hindenburg", "target_id": "papen", "target_label": "Papen",
         "target_is_entity": true, "predicate": "appointed", "claim_id": "c1",
         "claim_text": "Hindenburg appointed Papen", "source_document_id": "d1"},
        {"source_id": "hindenburg", "target_id": "literal:1932", "target_label": "1932",
         "target_is_entity": false, "predicate": "was re-elected in", "claim_id": "c2",
         "claim_text": "Hindenburg was re-elected in 1932", "source_document_id": "d1"},
        {"source_id": "hindenburg", "target_id": "literal:His Party", "target_label": "His Party",
         "target_is_entity": false, "predicate": "was believed to be among", "claim_id": "c3",
         "claim_text": "Hindenburg was believed to be among His Party", "source_document_id": "d1"}
      ],
      "truncated": false
    }
    """

    @Test func rebuildMakesNoNodeForALiteral() throws {
        let sim = GraphSimulation()
        sim.rebuild(from: try response(neighbourhood))
        #expect(sim.nodes.map(\.id).sorted() == ["hindenburg", "papen"])
        #expect(sim.edges.map(\.claimId) == ["c1"])
    }

    @Test func aStatementWithALiteralObjectIsCountedOnItsSubject() throws {
        let sim = GraphSimulation()
        sim.rebuild(from: try response(neighbourhood))
        #expect(sim.literalStatementCounts == ["hindenburg": 2])
    }

    @Test func aTappedLiteralIdNeverBecomesTheFocus() {
        #expect(GraphSimulation.entityFocusId(forTapped: "literal:1932") == nil)
        #expect(GraphSimulation.entityFocusId(forTapped: "papen") == "papen")
    }
}
