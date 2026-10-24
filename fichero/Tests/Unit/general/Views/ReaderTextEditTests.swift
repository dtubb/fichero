@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Typing in the Reader (#5154). What breaks without these: a split sent at a JavaScript offset the
/// engine counts differently (every character after an emoji shifts), a message read under the old names
/// the page no longer posts, or a typed correction that overwrites the reading it corrected.
struct ReaderTextEditTests {
    private func line(text: String? = "ܐܒܓܕ", version: Int? = 3) -> Segment {
        Segment(
            id: "l1", provisional: false, documentId: "p1", passId: "imported", kind: "line", kindRaw: nil,
            version: version, provenanceKind: .externalImport,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "p1", rect: [0.1, 0.2, 0.8, 0.05])),
            baseline: nil, text: text, confidence: nil, language: nil, script: nil, direction: "rtl",
            sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
        )
    }

    @Test("the three messages the page posts are read whole, or not at all")
    func parses() {
        #expect(ReaderTextEdit.message(from: [
            "kind": "readingEdit", "pageId": "p1", "segmentId": "l1", "text": "t", "previous": "s", "basedOn": "r1"
        ]) == .edited(pageId: "p1", segmentId: "l1", text: "t", basedOn: "r1"))
        #expect(ReaderTextEdit.message(from: [
            "kind": "readingEdit", "pageId": "p1", "segmentId": "l1", "text": "t", "previous": "s", "basedOn": NSNull()
        ]) == .edited(pageId: "p1", segmentId: "l1", text: "t", basedOn: nil))
        #expect(ReaderTextEdit.message(from: ["kind": "lineSplit", "pageId": "p1", "segmentId": "l1", "offset": 2])
                == .split(pageId: "p1", segmentId: "l1", offset: 2))
        #expect(ReaderTextEdit.message(from: ["kind": "lineJoin", "pageId": "p1", "segmentId": "l2", "intoSegmentId": "l1"])
                == .join(pageId: "p1", segmentId: "l2", intoSegmentId: "l1"))
        #expect(ReaderTextEdit.message(from: ["kind": "lineSplit", "pageId": "p1", "segmentId": "l1"]) == nil)
        // The names before the ruling are not read: the page does not post them.
        #expect(ReaderTextEdit.message(from: ["kind": "lineEdited", "pageId": "p1", "segmentId": "l1", "text": "t"]) == nil)
        #expect(ReaderTextEdit.message(from: ["kind": "lineJoin", "pageId": "p1", "segmentId": "l2", "previousSegmentId": "l1"]) == nil)
    }

    @Test("a JavaScript offset past an emoji is the engine's code-point offset")
    func utf16ToCodePoints() {
        #expect(ReaderTextEdit.codePointOffset(4, in: "a😀bc") == 3)   // a, 😀 (two UTF-16 units), b
        #expect(ReaderTextEdit.codePointOffset(2, in: "ܐܒܓܕ") == 2)    // Syriac: one unit each
    }

    @Test("Return mid-line: segment.split at the code-point offset in the SHOWN text, the version, no geometry")
    func splitParams() throws {
        let message = ReaderTextEdit.Message.split(pageId: "p1", segmentId: "l1", offset: 4)
        let request = try ReaderTextEdit.split(message, of: line(), shownText: "a😀bc").get()
        #expect(request == SegmentSplitRequest(segmentId: "l1", atOffset: 3, expectedVersion: 3))
        let json = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any])
        #expect(json.keys.sorted() == ["at_offset", "expected_version", "segment_id"], "no parts, no box: the engine cuts")
        #expect(json["segment_id"] as? String == "l1")
        #expect(json["at_offset"] as? Int == 3)
        #expect(json["expected_version"] as? Int == 3)
        // No reading counts: the box's own text is what the page shows.
        #expect(try ReaderTextEdit.split(message, of: line(), shownText: nil).get().atOffset == 4)
        #expect(ReaderTextEdit.split(message, of: line(version: nil), shownText: "abcd") == .failure(.versionUnknown))
        #expect(ReaderTextEdit.split(message, of: line(text: nil), shownText: nil) == .failure(.tooFew))
    }

    @Test("a Reader edit across lines is read whole and becomes ONE create_many; a stale or unknown line sends nothing")
    func readingEditsBecomeOneBatch() throws {
        let message = try #require(ReaderTextEdit.message(from: [
            "kind": "readingEdits", "pageId": "p1", "segmentId": "l1",
            "edits": [["segmentId": "l1", "text": "joined", "previous": "ab", "basedOn": "r1"]],
            "leftOut": ["l2"]
        ]))
        #expect(message == .editedMany(
            pageId: "p1", segmentId: "l1",
            readings: [.init(segmentId: "l1", text: "joined", basedOn: "r1")], leftOut: ["l2"]
        ))
        #expect(ReaderTextEdit.message(from: ["kind": "readingEdits", "pageId": "p1", "segmentId": "l1"]) == nil)

        var second = line()
        second = Segment(
            id: "l2", provisional: false, documentId: "p1", passId: "imported", kind: "line", kindRaw: nil,
            version: 7, provenanceKind: .externalImport, anchor: second.anchor, baseline: nil, text: "x",
            confidence: nil, language: nil, script: nil, direction: "rtl", sourceArtifactId: nil, boxIndex: 1,
            pageIndex: nil, metadata: nil
        )
        let params = try #require(ReaderTextEdit.newReadings(for: message, segments: [line(), second]))
        let json = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(params)) as? [String: Any])
        let left = try #require(json["left_out"] as? [[String: Any]])
        #expect(left.count == 1 && left[0]["segment_id"] as? String == "l2" && left[0]["expected_version"] as? Int == 7)
        #expect((json["readings"] as? [[String: Any]])?.first?["corrects_representation_id"] as? String == "r1")
        #expect(ReaderTextEdit.newReadings(for: message, segments: [line()]) == nil, "an unknown line is not guessed at")
    }

    @Test("a typed line is a NEW reading correcting the one typed over; the reply to the page is safe JSON")
    func newReadingAndReply() throws {
        let params = try #require(ReaderTextEdit.newReading(for: .edited(pageId: "p1", segmentId: "l1", text: "ܫܠܡܐ", basedOn: "r1")))
        let json = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(params)) as? [String: String])
        // The reading typed over is also the stale check's token (#5001): refused with a 409 if another counts now.
        #expect(json == ["document_id": "p1", "segment_id": "l1", "kind": "transcription", "content": "ܫܠܡܐ",
                         "corrects_representation_id": "r1", "expected_counting_id": "r1"])
        let fromWords = try #require(ReaderTextEdit.newReading(for: .edited(pageId: "p1", segmentId: "l1", text: "x", basedOn: nil)))
        let wordsJSON = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(fromWords)) as? [String: String])
        #expect(wordsJSON["corrects_representation_id"] == nil, "a line whose text came from its words corrects nothing")
        #expect(wordsJSON["expected_counting_id"] == nil, "and has no reading to check against")

        let refused = ReaderTextEdit.committedScript(pageId: "p1", segmentId: #"x"); y"#, reason: "stale")
        #expect(refused.hasPrefix("window.fichero?.lineCommitted?.({") && refused.hasSuffix("});"))
        let payload = String(refused.dropFirst("window.fichero?.lineCommitted?.(".count).dropLast(2))
        let answer = try #require(JSONSerialization.jsonObject(with: Data(payload.utf8)) as? [String: Any])
        #expect(answer["pageId"] as? String == "p1" && answer["ok"] as? Bool == false && answer["reason"] as? String == "stale")
        let taken = ReaderTextEdit.committedScript(pageId: "p1", segmentId: "l1", reason: nil)
        #expect(!taken.contains("reason") && taken.contains(#""ok":true"#))
    }
}
