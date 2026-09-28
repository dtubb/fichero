@testable import Fichero
import Testing

/// The Inspector's Making section at page level (#5149). What breaks without these: an imported page
/// that does not say which file it came from, a machine pass listed above the file's own, or "1 lines".
struct InspectorMakingTests {
    private func pass(_ id: String, name: String, file: String? = nil, format: String? = nil,
                      original: Bool = false, provisional: Bool = false) -> SegmentPassValue {
        SegmentPassValue(
            id: id, provisional: provisional, documentId: "page-1", name: name, provenanceKind: .workflow,
            importFile: file, importFormat: format, hasOriginal: original
        )
    }

    private func segment(_ id: String, kind: String, passId: String) -> Segment {
        Segment(
            id: id, provisional: false, documentId: "page-1", passId: passId, kind: kind, kindRaw: nil,
            provenanceKind: .workflow,
            anchor: SourceAnchorValue(generated: .init(documentId: "page-1")),
            baseline: nil, text: nil, confidence: nil, language: nil, script: nil, direction: nil,
            sourceArtifactId: nil, boxIndex: nil, pageIndex: nil, metadata: nil
        )
    }

    @Test("an imported pass says its file, its format and what it holds, first; a legacy pass is not listed")
    func importedPassFirst() {
        let entries = InspectorMaking.entries(
            passes: [
                pass("m", name: "Kraken lines"),
                pass("i", name: "0065.xml", file: "0065.xml", format: "pagexml", original: true),
                pass("legacy:a1", name: "transcription", provisional: true)
            ],
            segments: [
                segment("r1", kind: "region", passId: "i"),
                segment("l1", kind: "line", passId: "i"),
                segment("l2", kind: "line", passId: "i"),
                segment("m1", kind: "line", passId: "m")
            ]
        )
        #expect(entries.map(\.passId) == ["i", "m"])
        #expect(entries[0].title == "Imported from 0065.xml")
        #expect(entries[0].detail == "PAGE XML · 2 lines, 1 region")
        #expect(entries[0].hasOriginal)
        #expect(entries[1].title == "Kraken lines")
        #expect(entries[1].detail == "1 line")
        #expect(!entries[1].hasOriginal)
    }

    @Test("every import format has the name people write")
    func formatNames() {
        #expect(["pagexml", "alto", "tei", "hocr", "yolo", "other"].map(InspectorMaking.formatName)
                == ["PAGE XML", "ALTO", "TEI", "hOCR", "YOLO", "other"])
    }

    @Test("the working pass says so and why; the others offer to become it")
    func workingSaysWhy() {
        var chosen = pass("c", name: "mine")
        chosen.working = true
        chosen.workingBasis = "chosen"
        var byRule = pass("r", name: "file", file: "f.xml", format: "alto")
        byRule.working = true
        byRule.workingBasis = "human-touched"
        let other = pass("o", name: "other")
        let entries = InspectorMaking.entries(passes: [chosen, byRule, other], segments: [])
        let notes = Dictionary(uniqueKeysWithValues: entries.map { ($0.passId, $0.workingNote) })
        #expect(notes["c"] == "Working · chosen by a person")
        #expect(notes["r"] == "Working · by the project's rule")
        #expect(notes["o"] == .some(nil))
    }

    /// #5122: a georeferencing pass (control points and a mask) is listed APART, after the text passes,
    /// and is not offered as the page's working text pass. Listed among them, it read as another
    /// transcription a person could make the page's text.
    @Test("a georeferencing pass is listed after the text passes, flagged, with its format named")
    func georeferencingListedApart() {
        var georef = pass("g", name: "paris.georef.json", file: "paris.georef.json", format: "iiif-georef")
        georef.transformation = "polynomial-1"
        let entries = InspectorMaking.entries(
            passes: [georef, pass("m", name: "Kraken lines")],
            segments: [segment("c1", kind: "control-point", passId: "g"), segment("k1", kind: "mask", passId: "g")]
        )
        #expect(entries.map(\.passId) == ["m", "g"], "an imported georeference is not listed first")
        #expect(entries.map(\.georeferencing) == [false, true])
        #expect(entries[1].detail == "IIIF Georeference · 1 control-point, 1 mask")
    }
}
