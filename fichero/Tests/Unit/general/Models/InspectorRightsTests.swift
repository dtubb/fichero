@testable import Fichero
import Foundation
import Testing

/// The Inspector's Rights section (5.8). What breaks without these: a restriction shown as open, a
/// model rule missing from the words, a record placed on the wrong level, or a Set that sends facts
/// nobody chose (an empty label list would read as "no labels" to a reader of the record).
struct InspectorRightsTests {
    @Test("the effect says who may see it, where it may be sent, and its labels")
    func effectInWords() {
        let restricted = InspectorRights.effect(.init(restricted: true, readers: ["owner"], modelUse: "local",
                                                     labels: ["TK Attribution"]))
        #expect(restricted.map(\.value) == ["Only owner", "Local models only", "TK Attribution"])
        let open = InspectorRights.effect(.init())
        #expect(open.map(\.value) == ["Everyone the library's permissions allow",
                                      "No rule here; the library's AI settings decide"])
    }

    @Test("each record says where it sits and what it says, library first")
    func recordsPlaced() {
        let rows = InspectorRights.rows([
            .init(id: "r1", targetKind: "library", targetId: "library", holders: ["ÖNB"], labels: ["TK Attribution"]),
            .init(id: "r2", targetKind: "document", targetId: "p1", conditions: "agreement 2026-07", modelUse: "local"),
            .init(id: "r3", targetKind: "document", targetId: "folder"),
            .init(id: "r4", targetKind: "segment", targetId: "l1", restricted: true, readers: ["owner"], createdBy: "owner")
        ], targetKind: "segment", targetId: "l1", pageId: "p1")
        #expect(rows.map(\.place) == ["On the library", "On this page", "On a folder above", "On this segment"])
        #expect(rows[0].detail == "labels: TK Attribution · held by ÖNB")
        #expect(rows[1].detail == "local models only · agreement 2026-07")
        #expect(rows[3].detail == "restricted to owner · by owner")
    }

    @Test("Set sends only the fact chosen")
    func setSendsOnlyTheFact() throws {
        let rule = RightsSetRequest(targetKind: "segment", targetId: "l1", modelUse: "none")
        let json = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(rule)) as? [String: String])
        #expect(json == ["target_kind": "segment", "target_id": "l1", "model_use": "none"])
    }
}
