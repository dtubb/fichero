@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Typing in the Reader (#5154). What breaks without these: a split that cuts at a JavaScript offset
/// the engine counts differently (every character after an emoji shifts), a right-to-left line whose
/// FIRST words land in the LEFT box, or a typed correction that overwrites the reading it corrected.
struct ReaderTextEditTests {
    private func line(direction: String?, version: Int? = 3) -> Segment {
        Segment(
            id: "l1", provisional: false, documentId: "p1", passId: "imported", kind: "line", kindRaw: nil,
            version: version, provenanceKind: .externalImport,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "p1", rect: [0.1, 0.2, 0.8, 0.05])),
            baseline: nil, text: nil, confidence: nil, language: nil, script: nil, direction: direction,
            sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
        )
    }

    @Test("the three messages are read whole, or not at all")
    func parses() {
        #expect(ReaderTextEdit.message(from: ["kind": "lineEdited", "pageId": "p1", "segmentId": "l1", "text": "t", "basedOn": "r1"])
                == .edited(pageId: "p1", segmentId: "l1", text: "t", basedOn: "r1"))
        #expect(ReaderTextEdit.message(from: ["kind": "lineSplit", "pageId": "p1", "segmentId": "l1", "offset": 2, "text": "abcd"])
                == .split(pageId: "p1", segmentId: "l1", offset: 2, text: "abcd"))
        #expect(ReaderTextEdit.message(from: ["kind": "lineJoin", "pageId": "p1", "segmentId": "l2", "previousSegmentId": "l1"])
                == .join(pageId: "p1", segmentId: "l2", previousSegmentId: "l1"))
        #expect(ReaderTextEdit.message(from: ["kind": "lineSplit", "pageId": "p1", "segmentId": "l1", "text": "abcd"]) == nil)
        #expect(ReaderTextEdit.message(from: ["kind": "lineDeleted", "pageId": "p1", "segmentId": "l1"]) == nil)
    }

    @Test("a JavaScript offset past an emoji is the engine's code-point offset")
    func utf16ToCodePoints() {
        #expect(ReaderTextEdit.codePointOffset(4, in: "a😀bc") == 3)   // a, 😀 (two UTF-16 units), b
        #expect(ReaderTextEdit.codePointOffset(2, in: "ܐܒܓܕ") == 2)    // Syriac: one unit each
    }

    @Test("the box is cut in proportion along the direction; right-to-left's first part is the RIGHT one")
    func cutsFollowTheDirection() {
        let rect = [0.0, 0.0, 1.0, 0.5]
        #expect(ReaderTextEdit.cut(rect, at: 0.25, direction: "ltr") == ([0, 0, 0.25, 0.5], [0.25, 0, 0.75, 0.5]))
        #expect(ReaderTextEdit.cut(rect, at: 0.25, direction: "rtl") == ([0.75, 0, 0.25, 0.5], [0, 0, 0.75, 0.5]))
        #expect(ReaderTextEdit.cut(rect, at: 0.5, direction: "ttb") == ([0, 0, 1, 0.25], [0, 0.25, 1, 0.25]))
    }

    @Test("Return mid-line: two parts, the reading cut at the caret, the line's version sent")
    func splitParams() throws {
        let message = ReaderTextEdit.Message.split(pageId: "p1", segmentId: "l1", offset: 2, text: "abcd")
        let params = try ReaderTextEdit.split(message, of: line(direction: "rtl")).get()
        #expect(params.expectedVersion == 3)
        #expect(params.parts.map(\.readingSpan) == [[0, 2], [2, 4]])
        #expect(params.parts[0].anchor.rect[0] > params.parts[1].anchor.rect[0], "rtl: first words on the right")
        #expect(ReaderTextEdit.split(message, of: line(direction: nil, version: nil)) == .failure(.versionUnknown))
        let atEdge = ReaderTextEdit.Message.split(pageId: "p1", segmentId: "l1", offset: 0, text: "abcd")
        #expect(ReaderTextEdit.split(atEdge, of: line(direction: nil)) == .failure(.tooFew))
    }

    @Test("a typed line is a NEW reading correcting the one typed over; the reply to the page is safe JSON")
    func newReadingAndReply() throws {
        let params = try #require(ReaderTextEdit.newReading(for: .edited(pageId: "p1", segmentId: "l1", text: "ܫܠܡܐ", basedOn: "r1")))
        let json = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(params)) as? [String: String])
        #expect(json == ["document_id": "p1", "segment_id": "l1", "kind": "transcription", "content": "ܫܠܡܐ",
                         "corrects_representation_id": "r1"])
        let script = ReaderTextEdit.committedScript(kind: "lineEdited", segmentId: #"x"); y"#, succeeded: true, detail: "")
        #expect(script.hasPrefix("window.fichero?.lineCommitted?.({") && script.hasSuffix("});"))
    }
}
