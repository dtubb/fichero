@testable import Fichero
import Foundation
import Testing

/// The Inspector's Certainty and Damage section (5.5). What breaks without these: a gap drawn in words
/// at the wrong letter, a file's claim shown as a person's, a scholar's certainty confused with a
/// machine's confidence, or a Mark sent with a span the engine counts differently (a Syriac or emoji
/// reading measured in UTF-16).
struct InspectorEditorialTests {
    @Test("each fact says where, how much, why, who and how sure -- a file's claim is the file's")
    func rowsSayEverything() {
        let rows = InspectorEditorial.rows([
            .init(id: "f1", kind: "unclear", charStart: 0, charEnd: 3, reason: "faded", certainty: 0.8, createdBy: "owner"),
            .init(id: "f2", kind: "lost", charStart: 5, extentQuantity: 2, extentUnit: "character", reason: "a hole",
                  createdBy: "owner", source: "file: p.flor.2.133.xml"),
            .init(id: "f3", kind: "added", charStart: 4, charEnd: 5, place: "above"),
            .init(id: "f4", kind: "lost", extent: "unknown")
        ])
        #expect(rows.map(\.title) == ["Unclear", "Lost", "Added by the scribe", "Lost"])
        #expect(rows[0].detail == "letters 1–3 · faded · by owner · sure 80%")
        #expect(rows[1].detail == "after letter 5 · 2 characters · a hole · from the file p.flor.2.133.xml")
        #expect(rows[2].detail == "letter 5 · above the line")
        #expect(rows[3].detail == "the whole segment · unknown")
    }

    @Test("a Mark covers the whole counting reading, counted in code points; no reading, no Mark")
    func markSpansTheWholeReadingInCodePoints() throws {
        let reading = InspectorText.Reading(
            id: "r1", kind: "transcription", content: "a😀b", maker: "human", author: nil, guideline: nil, pairId: nil, pairRole: nil
        )
        let params = try #require(InspectorEditorial.record(.unclear, segmentId: "s1", reading: reading))
        #expect(params == EditorialRecordRequest(
            segmentId: "s1", kind: "unclear", representationId: "r1", charStart: 0, charEnd: 3, place: nil
        ))
        #expect(InspectorEditorial.record(.added, segmentId: "s1", reading: reading)?.place == "above")
        #expect(InspectorEditorial.record(.unclear, segmentId: "s1", reading: nil) == nil)
        let json = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(params)) as? [String: Any])
        #expect(json["place"] == nil, "an unset place is not sent")
        #expect(json["representation_id"] as? String == "r1")
    }
}
