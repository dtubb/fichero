@testable import Fichero
import Foundation
import Testing

/// #6082: Hands, Certainty and Rights on a multi-selection are one engine action each, over the stored lines only.
struct SegmentBulkEditTests {
    private func json<T: Encodable>(_ value: T) throws -> [String: Any] {
        try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(value)) as? [String: Any])
    }

    @Test("a hand is attributed to every stored line in one request; a provisional id is left out")
    func handKeys() throws {
        let call = try SegmentBulkEdit.attributeHand("hand-1", to: ["a", "legacy:x:0", "b"], certainty: 0.5).get()
        let sent = try json(call)
        #expect(sent["hand_id"] as? String == "hand-1")
        #expect(sent["segment_ids"] as? [String] == ["a", "b"])
        #expect(sent["certainty"] as? Double == 0.5)
    }

    @Test("an editorial fact names its kind and every line; no certainty key when none")
    func editorialKeys() throws {
        let sent = try json(try SegmentBulkEdit.record("unclear", on: ["a", "b"]).get())
        #expect(sent["kind"] as? String == "unclear")
        #expect(sent["segment_ids"] as? [String] == ["a", "b"])
        #expect(sent["certainty"] == nil)
    }

    @Test("rights name each line as a segment target and carry model_use")
    func rightsKeys() throws {
        let sent = try json(try SegmentBulkEdit.setRights(on: ["a", "b"], restricted: true, readers: ["me"], modelUse: "local").get())
        let targets = try #require(sent["targets"] as? [[String: String]])
        #expect(targets == [["kind": "segment", "id": "a"], ["kind": "segment", "id": "b"]])
        #expect(sent["restricted"] as? Bool == true)
        #expect(sent["readers"] as? [String] == ["me"])
        #expect(sent["model_use"] as? String == "local")
    }

    @Test("nothing stored is refused in words; more than the engine takes is refused before sending")
    func refusals() {
        #expect(SegmentBulkEdit.lines([]) == .failure(.nothingSelected))
        #expect(SegmentBulkEdit.lines(["legacy:x:0"]) == .failure(.nothingSelected))
        let many = (0...SegmentBulkEdit.cap).map { "s\($0)" }
        #expect(SegmentBulkEdit.lines(many) == .failure(.tooMany(many.count)))
        #expect(SegmentBulkEdit.Refusal.nothingSelected.words == "Select a line first.")
    }

    @Test("the step is named by how many lines it holds")
    func stepName() {
        #expect(SegmentBulkEdit.stepName("Set Rights on", count: 1) == "Set Rights on Line")
        #expect(SegmentBulkEdit.stepName("Set Rights on", count: 3) == "Set Rights on 3 Lines")
    }
}
