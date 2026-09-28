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
}
