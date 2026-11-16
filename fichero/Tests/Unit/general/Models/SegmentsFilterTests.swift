@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

// Spec: source.editor.segments-list-has-a-filter-bar (#6476) and the first slice of
// source.editor.segment-row-shows-its-facts-as-icons (#6482), source/segment-editor-crud.md.
//
// A row's facts (its count, its direction, language and script, own or from a parent, and its
// reading's state) come from the page's segments alone (`SegmentRowFacts`); the filter keeps the
// rows that match and their ancestors, so a line keeps its region (`SegmentsFilter`).

@Suite("Segments pane: a row's facts, and the filter that keeps matches with their ancestors")
struct SegmentsFilterTests {

    private func segment(
        _ id: String, kind: String, parent: String? = nil, text: String? = nil, human: Bool = false,
        confidence: Double? = nil, language: String? = nil, script: String? = nil, direction: String? = nil
    ) -> Segment {
        var made = Segment(
            id: id, provisional: false, documentId: "p1", passId: "p", kind: kind, kindRaw: nil,
            parentSegmentId: parent, provenanceKind: human ? .human : .externalImport,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "p1")),
            baseline: nil, text: text, confidence: confidence, sourceArtifactId: nil, boxIndex: nil, pageIndex: nil, metadata: nil
        )
        made.language = language
        made.script = script
        made.direction = direction
        return made
    }

    /// Two regions: a Spanish one with three lines (one a person's, one doubtful, one unread) and a Latin note.
    private var page: [Segment] {
        [
            segment("r1", kind: "region", language: "es", script: "Latn", direction: "ltr"),
            segment("l1", kind: "line", parent: "r1", text: "Vn hisopo y Cadereta de cobre", human: true),
            segment("l2", kind: "line", parent: "r1", text: "tumba = Vn Ataud", confidence: 0.42),
            segment("l3", kind: "line", parent: "r1"),
            segment("w1", kind: "word", parent: "l1", text: "hisopo"),
            segment("r2", kind: "region", language: "la"),
            segment("l4", kind: "line", parent: "r2", text: "In capellá", confidence: 0.95)
        ]
    }

    private func facts(_ id: String) throws -> SegmentRowFacts {
        SegmentRowFacts.of(try #require(page.first { $0.id == id }), in: page)
    }

    @Test("a region counts its lines, a line its words, a word its characters")
    func counts() throws {
        #expect(try facts("r1").count == .lines(3))
        #expect(try facts("l1").count == .words(6))
        #expect(try facts("w1").count == .characters(6))
        #expect(try facts("l3").count == nil)
    }

    @Test("language, script and direction are the segment's own, else the nearest parent's, which is named")
    func inherited() throws {
        #expect(try facts("r1").language == .init(value: "es", fromSegmentId: nil))
        #expect(try facts("w1").language == .init(value: "es", fromSegmentId: "r1"))
        #expect(try facts("w1").direction?.inherited == true)
        #expect(try facts("l4").language == .init(value: "la", fromSegmentId: "r2"))
        #expect(try facts("l4").script == nil)
    }

    @Test("a reading is a person's, a machine's, doubtful below the floor, or missing")
    func readingStates() throws {
        #expect(try facts("l1").reading == .person)
        #expect(try facts("l2").reading == .doubtful(0.42))
        #expect(try facts("l3").reading == SegmentRowFacts.ReadingState.none)
        #expect(try facts("l4").reading == .machine)
        #expect(try facts("r1").reading == .notRead)
    }

    @Test("no filter shows everything")
    func noFilter() {
        let result = SegmentsFilter().apply(to: page)
        #expect(!SegmentsFilter().isActive)
        #expect(result.shown == Set(page.map(\.id)))
    }

    @Test("a query matches the words, case- and accent-blind, and keeps the region above the line")
    func queryKeepsAncestors() {
        let result = SegmentsFilter(query: "CAPELLA").apply(to: page)
        #expect(result.matched == ["l4"])
        #expect(result.shown == ["l4", "r2"])
    }

    @Test("Kind keeps only that kind, its ancestors shown with it")
    func kindFacet() {
        let result = SegmentsFilter(kinds: ["word"]).apply(to: page)
        #expect(result.matched == ["w1"])
        #expect(result.shown == ["w1", "l1", "r1"])
    }

    @Test("Reading, Low Confidence and Flagged narrow to those rows")
    func readingFacets() {
        #expect(SegmentsFilter(reading: SegmentsFilter.Reading.none).apply(to: page).matched == ["l3"])
        #expect(SegmentsFilter(reading: .person).apply(to: page).matched == ["l1"])
        #expect(SegmentsFilter(reading: .machine).apply(to: page).matched == ["l2", "l4", "w1"])
        #expect(SegmentsFilter(doubtfulOnly: true).apply(to: page).matched == ["l2"])
        #expect(SegmentsFilter(flaggedOnly: true).apply(to: page, flagged: ["l4"]).matched == ["l4"])
    }

    @Test("Language matches a value inherited from the region")
    func languageFacet() {
        #expect(SegmentsFilter(kinds: ["line"], languages: ["la"]).apply(to: page).matched == ["l4"])
    }

    @Test("the bar says how many match of how many")
    func countLine() {
        #expect(SegmentsFilter.countLine(matched: 12, of: 34) == "12 of 34")
    }

    @Test("the outline keeps only the rows the filter shows, nested as before")
    func outlineIsPruned() {
        let shown = SegmentsFilter(query: "ataud").apply(to: page).shown
        let rows = SegmentsPane.pruned(SegmentsPane.outline(page, top: ["r1", "r2"]), keeping: shown)
        #expect(rows.map(\.segmentId) == ["r1"])
        #expect(rows.first?.children.map(\.segmentId) == ["l2"])
        #expect(SegmentsPane.pruned(SegmentsPane.outline(page, top: ["r1", "r2"]), keeping: nil).count == 2)
    }

    @Test("the facet menu offers only the values the page holds")
    func optionsComeFromThePage() {
        let options = SegmentsFilter.options(in: page)
        #expect(options.kinds == ["line", "region", "word"])
        #expect(options.languages == ["es", "la"])
        #expect(options.directions == ["ltr"])
    }

    @Test("every row's facts in one pass are the same as each row's own")
    func allMatchesEach() throws {
        let all = SegmentRowFacts.all(in: page)
        for segment in page {
            #expect(all[segment.id] == SegmentRowFacts.of(segment, in: page))
        }
    }

    @Test("the Show in Rows choice: every fact by default, saved by name, unknown names ignored")
    func shownRoundTrips() {
        #expect(SegmentRowFacts.Shown.decode("all") == Set(SegmentRowFacts.Shown.allCases))
        #expect(SegmentRowFacts.Shown.decode("count,reading,bogus") == [.count, .reading])
        #expect(SegmentRowFacts.Shown.encode([.reading, .count]) == "count,reading")
        #expect(SegmentRowFacts.Shown.encode(Set(SegmentRowFacts.Shown.allCases)) == "all")
        #expect(SegmentRowFacts.Shown.decode(SegmentRowFacts.Shown.encode([])) == [])
    }

    @Test("a row's direction arrow and a doubtful reading's percent")
    func factWords() {
        #expect(SegmentRowFactsView.arrow("rtl") == "arrow.left")
        #expect(SegmentRowFactsView.arrow("ltr") == "arrow.right")
        #expect(SegmentRowFactsView.percent(0.424) == "42%")
        #expect(SegmentRowFactsView.tooltip("Language es", .init(value: "es", fromSegmentId: "r1"), { _ in "its region" })
            == "Language es, from its region")
    }

    @Test("a region is numbered among the page's regions in every list; any other row by its place (#6476)")
    func oneRegionNumbering() {
        let page = [segment("r1", kind: "region"), segment("l1", kind: "line", parent: "r1"),
                    segment("l2", kind: "line", parent: "r1"), segment("r2", kind: "region")]
        #expect(SegmentsPane.numberingPlace(of: page[3], at: 3, among: page) == 1)
        #expect(SegmentsPane.rowLabel(page[3], at: SegmentsPane.numberingPlace(of: page[3], at: 3, among: page))
                .hasPrefix("Region 2"))
        #expect(SegmentsPane.numberingPlace(of: page[2], at: 5, among: page) == 5)
        #expect(SegmentsPane.numberingPlace(of: nil, at: 4, among: page) == 4)
    }

    @Test("the list starts with the page: its name and what it holds, at the top level only (#6415)")
    func pageRowComesFirst() {
        let page = [segment("r1", kind: "region"), segment("l1", kind: "line", parent: "r1"),
                    segment("l2", kind: "line", parent: "r1")]
        #expect(SegmentsPane.pageRow(name: "7_Hoja_4_Recto.JPG", segments: page, parentId: nil)
                == .init(title: "7_Hoja_4_Recto.JPG", detail: "2 lines, 1 region"))
        #expect(SegmentsPane.pageRow(name: "p", segments: page, parentId: "r1") == nil, "not inside a region")
        #expect(SegmentsPane.pageRow(name: "p", segments: [], parentId: nil) == nil, "nothing listed, no page row")
    }
}
