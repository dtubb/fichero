@testable import Fichero
import FicheroAPIClient
import Testing

/// Regions in distinct colours, lines in alternating tints (#5200, #5207; Daniel on the clm13027 page: the
/// boxes overlapped into stacked filled bands). What breaks without these: a region's colour changes between
/// launches (Swift's hashValue is seeded per launch), a line takes a colour other than its region's, or two
/// neighbouring lines of a region get the same tint.
struct RegionColoursTests {
    private func segment(_ id: String, kind: String, parent: String? = nil, at index: Int) -> Segment {
        Segment(
            id: id, provisional: false, documentId: "p1", passId: "p", kind: kind, kindRaw: nil,
            parentSegmentId: parent, provenanceKind: .externalImport,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "p1")),
            baseline: nil, text: nil, confidence: nil, sourceArtifactId: nil, boxIndex: index, pageIndex: nil, metadata: nil
        )
    }

    @Test("a region's place in the palette is the same on every launch and every machine")
    func stableHash() {
        // FNV-1a over UTF-8, mod 12, computed independently of the app.
        #expect(RegionColours.paletteIndex(for: "seg-region-0001") == 3)
        #expect(RegionColours.paletteIndex(for: "r1") == 4)
        #expect(RegionColours.paletteIndex(for: "r2") == 1)
    }

    @Test("lines and words take their region's colour; a region's lines alternate tints in its order")
    func tones() {
        let tones = RegionColours.tones(of: [
            segment("r1", kind: "region", at: 0),
            segment("l1", kind: "line", parent: "r1", at: 1),
            segment("w1", kind: "word", parent: "l1", at: 2),
            segment("l2", kind: "line", parent: "r1", at: 3),
            segment("l3", kind: "line", parent: "r1", at: 4),
            segment("r2", kind: "region", at: 5),
            segment("l4", kind: "line", parent: "r2", at: 6),
            segment("loose", kind: "line", at: 7)
        ])
        #expect(tones["w1"]?.regionId == "r1", "a word is its line's region's colour")
        #expect(["l1", "l2", "l3"].map { tones[$0]?.alternate } == [false, true, false], "alternating in order")
        #expect(tones["l4"] == .init(regionId: "r2", alternate: false), "each region starts on the full tint")
        #expect(tones["loose"]?.regionId == "loose", "a line with no region is its own colour")
    }

    #if os(macOS)
    @Test("the palette is as long as the hash's range, all system colours")
    func paletteSize() {
        #expect(SelectionStyle.regionPalette.count == RegionColours.paletteCount)
    }
    #endif
}
