@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The Segments list's other readings (`source.editor.segment-row-is-the-same-in-every-lens`, #6492): ticked readers' words
/// under a row, labelled, and the row's words are the counting reading's.
struct SegmentOtherReadingsTests {
    private func answer() throws -> Components.Schemas.CompareReadersResponse {
        let json = #"""
        {"page_id":"p1",
         "readers":[{"id":"a","label":"Kraken","kind":"candidate"},{"id":"b","label":"Gemini","kind":"candidate"}],
         "lines":[
          {"segment_id":"s1","order":0,"differs":true,"picked_by_person":false,"words":[],"counting_reader_id":"b",
           "readings":[{"reader_id":"a","text":"Yten dixo"},{"reader_id":"b","text":"Item dixo "}]},
          {"segment_id":"s2","order":1,"differs":false,"picked_by_person":false,"words":[],
           "readings":[{"reader_id":"a","text":"la capilla"}]},
          {"order":2,"differs":false,"picked_by_person":false,"words":[],
           "readings":[{"reader_id":"a","text":"no segment"}]}
         ]}
        """#
        return try JSONDecoder().decode(Components.Schemas.CompareReadersResponse.self, from: Data(json.utf8))
    }

    @Test("ticked readers' words come under a row in the readers' order, labelled; unticked and unread give nothing")
    func tickedReadersUnderTheRow() throws {
        let other = SegmentOtherReadings(answer: try answer())
        #expect(other.readers.map(\.label) == ["Kraken", "Gemini"])
        #expect(other.under("s1", ticked: ["Gemini", "Kraken"]) == [.init(reader: "Kraken", text: "Yten dixo"),
                                                                      .init(reader: "Gemini", text: "Item dixo")])
        #expect(other.under("s1", ticked: []).isEmpty)
        #expect(other.under("s2", ticked: ["Gemini"]).isEmpty)
        #expect(other.under("missing", ticked: ["Kraken"]).isEmpty)
    }

    @Test("a row shows the counting reading's words; where none counts it keeps its own text")
    func rowShowsTheCountingReading() throws {
        let other = SegmentOtherReadings(answer: try answer())
        #expect(other.shown("s1") == "Item dixo ")
        #expect(other.shown("s2") == nil)
    }

    @Test("the ticks are kept per window as labels, one per line")
    func ticksRoundTrip() {
        #expect(SegmentOtherReadings.decode(SegmentOtherReadings.encode(["Kraken", "Gemini"])) == ["Kraken", "Gemini"])
        #expect(SegmentOtherReadings.decode("").isEmpty)
    }

    @Test("the row's label is made from the shown words; with none counting it keeps the segment's own")
    func rowLabelUsesTheShownWords() {
        let line = Segment(
            id: "s1", provisional: false, documentId: "p1", passId: "p", kind: "line", kindRaw: nil,
            parentSegmentId: nil, provenanceKind: .externalImport,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "p1")),
            baseline: nil, text: "Yten dixo", confidence: nil, sourceArtifactId: nil, boxIndex: nil, pageIndex: nil, metadata: nil
        )
        #expect(SegmentsPane.showing("Item dixo", on: line)?.text == "Item dixo")
        #expect(SegmentsPane.showing(nil, on: line)?.text == "Yten dixo")
        #expect(SegmentsPane.showing("Item", on: nil) == nil)
    }
}
