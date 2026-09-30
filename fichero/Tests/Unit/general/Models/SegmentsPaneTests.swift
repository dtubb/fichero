@testable import Fichero
import FicheroAPIClient
import Testing

/// The Segments pane (#4942). What breaks without these: a row offered to open with nothing inside,
/// a path that names ids instead of levels, or a row that reads as an id.
struct SegmentsPaneTests {
    private func segment(_ id: String, kind: String, parent: String? = nil, text: String? = nil) -> Segment {
        Segment(
            id: id, provisional: false, documentId: "p1", passId: "p", kind: kind, kindRaw: nil,
            parentSegmentId: parent, provenanceKind: .externalImport,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "p1")),
            baseline: nil, text: text, confidence: nil, sourceArtifactId: nil, boxIndex: nil, pageIndex: nil, metadata: nil
        )
    }

    @Test("a row opens only when the segment holds others; the path names each level down to it")
    func openAndPath() {
        let segments = [
            segment("r1", kind: "region"),
            segment("l1", kind: "line", parent: "r1", text: "ܐܒܪܗܡ"),
            segment("w1", kind: "word", parent: "l1")
        ]
        #expect(SegmentsPane.hasChildren("r1", in: segments))
        #expect(SegmentsPane.hasChildren("l1", in: segments))
        #expect(!SegmentsPane.hasChildren("w1", in: segments))
        #expect(SegmentsPane.path(pageTitle: "fol. 1r", to: nil, in: segments).map(\.title) == ["fol. 1r"])
        let path = SegmentsPane.path(pageTitle: "fol. 1r", to: "l1", in: segments)
        #expect(path.map(\.title) == ["fol. 1r", "Region", "Line"])
        #expect(path.map(\.segmentId) == [nil, "r1", "l1"])
    }

    @Test("a row reads as its kind and its words, or its kind and place when it has none")
    func rowLabels() {
        // The words are an isolate (#5199): FSI...PDI with no direction resolved, RLI...PDI for an rtl line.
        #expect(SegmentsPane.rowLabel(segment("l1", kind: "line", text: " ܐܒ "), at: 0) == "Line · \u{2068}ܐܒ\u{2069}")
        #expect(SegmentsPane.rowLabel(segment("l1", kind: "line", text: "ܐܒ"), at: 0, direction: "rtl") == "Line · \u{2067}ܐܒ\u{2069}")
        #expect(SegmentsPane.rowLabel(segment("r1", kind: "region"), at: 2) == "Region 3")
        #expect(SegmentsPane.rowLabel(nil, at: 0) == "Segment 1")
        #expect(SegmentsPane.rowLabel(segment("l2", kind: "line"), at: 1) == "Line 2 · No reading", "a line with no reading says so")
    }
}

/// The three ways the pane shows a level (`source.segments-pane.views`): a list, a strip, a grid.
struct SegmentsPaneLensTests {
    @Test("list, strip and grid, each with its own name and symbol")
    func threeLenses() {
        #expect(SegmentsPane.Lens.allCases == [.list, .strip, .grid])
        #expect(SegmentsPane.Lens.allCases.map(\.title) == ["List", "Strip", "Grid"])
        #expect(Set(SegmentsPane.Lens.allCases.map(\.icon)).count == 3)
    }
}

/// A folder of laid-out pages with no named order (#5204, #5205, Daniel 2026-09-28: the Segments pane said
/// "No Reading Order" and the Reader showed only the folder while the Preview drew page 1's boxes). What
/// breaks without these: the panes beside the Preview read the FOLDER, or a page with no order lists nothing.
@MainActor
struct FolderOfPagesPanesTests {
    private func segment(_ id: String, kind: String, parent: String? = nil) -> Segment {
        Segment(
            id: id, provisional: false, documentId: "p1", passId: "legacy:a", kind: kind, kindRaw: nil,
            parentSegmentId: parent, provenanceKind: .externalImport,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "p1")),
            baseline: nil, text: nil, confidence: nil, sourceArtifactId: nil, boxIndex: nil, pageIndex: nil, metadata: nil
        )
    }

    @Test("with no named order a level lists as the engine served it, never re-sorted")
    func asWrittenKeepsTheServedOrder() {
        let segments = [
            segment("r2", kind: "region"), segment("l2", kind: "line", parent: "r2"),
            segment("r1", kind: "region"), segment("l1", kind: "line", parent: "r1"),
            segment("l0", kind: "line", parent: "a-region-not-on-this-page")
        ]
        #expect(SegmentsPane.asWritten(segments, under: nil) == ["r2", "r1", "l0"], "a parent off the page is the top")
        #expect(SegmentsPane.asWritten(segments, under: "r1") == ["l1"])
        #expect(SegmentsPane.shownOrAsWritten([], segments, under: nil) == ["r2", "r1", "l0"], "an empty order is no order")
        #expect(SegmentsPane.shownOrAsWritten(["r1"], segments, under: nil) == ["r1"], "a named order wins")
    }

    @Test("Create Named Order sends a conversion with no edit, which the engine takes as the eager form")
    func createNamedOrderBody() {
        // The request's ONLY key: `artifact_id` and `edit` travel together or not at all, and a body
        // with neither is the engine's eager conversion.
        #expect(ConvertPageRequest.CodingKeys.documentId.rawValue == "document_id")
        #expect(ConvertPageRequest(documentId: "p1") == .init(documentId: "p1"))
    }

    /// #5300 (ruled 2026-09-30): a selected folder is the folder in every pane. The Preview used to
    /// show its first file and the Inspector, Segments pane and Reader followed that file, so three
    /// panes described one item inside the folder. If `FolderPageShown` or `pageShown` comes back,
    /// the panes are describing the wrong thing again.
    @Test("a selected folder is the folder in every pane, not its first file")
    func aFolderIsItselfInEveryPane() throws {
        for path in [
            "Views/Inspector/Document/DocumentInspector+Sections.swift",
            "Views/Shell/ContentView/Layout/ContentView+PaneSpecs.swift",
            "Views/Shell/ContentView/Layout/ContentView+DetailLayout.swift",
            "Views/Preview/FolderContentsPreview.swift"
        ] {
            let source = try AppSource.text(path)
            #expect(!source.contains("FolderPageShown("), "\(path) resolves a folder to its first file again")
            #expect(!source.contains("pageShown(in:"), "\(path) resolves a folder to its first file again")
        }
    }

    @Test("the page's own order says whether the file gave it or the layout found it (#5216)")
    func pagesOwnOrderSaysWhereItCameFrom() {
        let fromFile = ReadingOrderSummary(id: "o1", name: "as-written", kind: "as-written", provenanceKind: "external_import")
        let fromLayout = ReadingOrderSummary(id: "o2", name: "as-written", kind: "as-written", provenanceKind: "workflow")
        #expect(ReadingOrderChoice.title(fromFile) == "Order: As in the File")
        #expect(ReadingOrderChoice.title(fromLayout) == "Layout Order", "a recogniser's order is not the file's")
        #expect(ReadingOrderChoice.help(fromFile) != ReadingOrderChoice.help(fromLayout))
        #expect(ReadingOrderChoice.title(ReadingOrderSummary(id: "o3", name: "Mine", kind: "imposed")) == "Mine")
    }
}
