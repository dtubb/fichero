@testable import Fichero
import FicheroAPIClient
import Testing

/// `segment-editor.md` "Box colour and the segment hierarchy" (ruled 2026-10-04, #5426, #5463): a box's colour
/// is its REGION's hue, shaded along the working pass's reading order; nothing is coloured at random. What
/// breaks without these: a region-less line gets its own hashed colour again (every line of a Kraken page a
/// different, unrelated colour), two regions share a hue, the shade stops following the order (so a moved line
/// does not show it moved), or the colour changes between draws of the same page.
struct RegionColoursTests {
    private func segment(_ id: String, kind: String, parent: String? = nil, at index: Int) -> Segment {
        Segment(
            id: id, provisional: false, documentId: "p1", passId: "p", kind: kind, kindRaw: nil,
            parentSegmentId: parent, provenanceKind: .externalImport,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "p1")),
            baseline: nil, text: nil, confidence: nil, sourceArtifactId: nil, boxIndex: index, pageIndex: nil, metadata: nil
        )
    }

    /// Two regions, three lines in the first (one with a word), one in the second.
    private var page: [Segment] {
        [
            segment("r1", kind: "region", at: 0),
            segment("l1", kind: "line", parent: "r1", at: 1),
            segment("w1", kind: "word", parent: "l1", at: 2),
            segment("l2", kind: "line", parent: "r1", at: 3),
            segment("l3", kind: "line", parent: "r1", at: 4),
            segment("r2", kind: "region", at: 5),
            segment("l4", kind: "line", parent: "r2", at: 6)
        ]
    }

    @Test("source.editor.colour.region-hue: each region its own hue, in reading order; its lines and words take it")
    func regionHue() throws {
        let tones = RegionColours.tones(of: page)
        let first = try #require(tones["r1"]), second = try #require(tones["r2"])
        #expect(first.hue != second.hue, "two regions on a page never share a hue")
        #expect([first.hue, second.hue] == [RegionColours.hue(ofRegion: "r1"), RegionColours.hue(ofRegion: "r2")],
                "a region's hue is a fixed hash of its id, not its place")
        #expect(["l1", "w1", "l2", "l3"].allSatisfy { tones[$0]?.hue == first.hue }, "a region's lines and words are its hue")
        #expect(tones["l4"]?.hue == second.hue)
        #expect(tones["w1"] == tones["l1"], "a word takes its line's shade")
    }

    @Test("source.editor.colour.reading-order-gradient: lines shade from light to dark in reading order; reordering moves the shade")
    func gradientFollowsTheOrder() {
        let asWritten = RegionColours.tones(of: page)
        let shades = ["l1", "l2", "l3"].compactMap { asWritten[$0]?.strength }
        let expected = [RegionColours.lightestStrength, (1 + RegionColours.lightestStrength) / 2, 1]
        #expect(zip(shades, expected).allSatisfy { abs($0 - $1) < 1e-9 } && shades.count == 3,
                "evenly spaced from the lightest to full strength, first line lightest, last darkest")
        #expect(asWritten["l4"]?.strength == 1, "a region with one line draws it at full strength")

        // The pane's chosen order puts l3 first: the shades follow the order, not the box order.
        let reordered = RegionColours.tones(of: page, readingOrder: ["r1", "l3", "l1", "l2", "r2", "l4"])
        #expect(["l3", "l1", "l2"].compactMap { reordered[$0]?.strength } == shades, "the shade moves with the line")
        #expect(reordered["r1"]?.hue == asWritten["r1"]?.hue, "the hue is the region's, not the line's place")
    }

    @Test("source.editor.display-menu-has-order-switches: each line's reading number runs down the page, regions and words have none")
    func orderNumbers() {
        let asWritten = RegionColours.orderNumbers(of: page)
        #expect(asWritten == ["l1": 1, "l2": 2, "l3": 3, "l4": 4])
        let reordered = RegionColours.orderNumbers(of: page, readingOrder: ["r1", "l3", "l1", "l2", "r2", "l4"])
        #expect(reordered["l3"] == 1 && reordered["l1"] == 2 && reordered["l2"] == 3 && reordered["l4"] == 4,
                "the numbers follow the chosen order")
    }

    @Test("source.editor.colour.shade-is-a-display-option: with the shade off every line is full strength and the hue stays")
    func shadeCanBeOff() {
        let on = RegionColours.tones(of: page, shadeByOrder: true)
        let off = RegionColours.tones(of: page, shadeByOrder: false)
        #expect(["l1", "l2", "l3"].compactMap { off[$0]?.strength } == [1, 1, 1], "no gradient")
        #expect(off["l2"]?.hue == on["l2"]?.hue, "the region's hue is unchanged")
    }

    @Test("source.editor.colour.never-random + regionless-lines-are-one-region: region-less lines share the page's one hue")
    func regionlessLinesAreOneRegion() throws {
        // A page whose lines have no region, after a region: the implicit region takes the next hue, at the
        // place its first line falls, and its lines grade along their order.
        let loose = [
            segment("r1", kind: "region", at: 0),
            segment("l1", kind: "line", parent: "r1", at: 1),
            segment("a", kind: "line", at: 2),
            segment("b", kind: "line", at: 3),
            segment("c", kind: "line", at: 4)
        ]
        let tones = RegionColours.tones(of: loose)
        let hues = Set(["a", "b", "c"].compactMap { tones[$0]?.hue })
        #expect(hues == [1], "every region-less line is one hue: the page's implicit region, next after r1")
        let shades = ["a", "b", "c"].compactMap { tones[$0]?.strength }
        #expect(shades == shades.sorted(by: <) && Set(shades).count == 3, "graded along the reading order, light to dark")
        #expect(RegionColours.tones(of: Array(loose.reversed())) == tones, "the same page draws the same every time")
        // The ids that used to pick colours by hash pick nothing now: renaming them changes no colour.
        let renamed = loose.map { (segment: Segment) -> Segment in
            var copy = segment
            copy.id = "x-" + segment.id
            copy.parentSegmentId = segment.parentSegmentId.map { "x-" + $0 }
            return copy
        }
        let renamedTones = RegionColours.tones(of: renamed)
        #expect(["a", "b", "c", "r1", "l1"].map { tones[$0] } == ["a", "b", "c", "r1", "l1"].map { renamedTones["x-" + $0] })
    }

    @Test("a page of one-line regions (Kraken's) steps through the hues in order, not a scatter")
    func oneLineRegionsStep() {
        let kraken = (0..<3).flatMap { index in
            [segment("r\(index)", kind: "region", at: index * 2),
             segment("l\(index)", kind: "line", parent: "r\(index)", at: index * 2 + 1)]
        }
        let tones = RegionColours.tones(of: kraken)
        #expect((0..<3).map { tones["l\($0)"]?.hue } == (0..<3).map { RegionColours.hue(ofRegion: "r\($0)") })
    }

    @Test("source.editor.colour.region-hue: deleting a region does not recolour the others")
    func deletingARegionKeepsTheOthersColours() throws {
        let before = RegionColours.tones(of: page)
        let withoutFirst = page.filter { !["r1", "l1", "w1", "l2", "l3"].contains($0.id) }
        let after = RegionColours.tones(of: withoutFirst)
        #expect(after["r2"]?.hue == before["r2"]?.hue, "r2 keeps its colour when r1 goes")
        #expect(after["l4"]?.hue == before["l4"]?.hue)
    }

    @Test("the palette is as long as the hue range, and a box with no tone is the plain accent")
    func palette() {
        #expect(SelectionStyle.regionPalette.count == RegionColours.paletteCount)
        #expect(SelectionStyle.regionColour(.init(hue: 13, strength: 1)) == SelectionStyle.regionColour(.init(hue: 1, strength: 1)),
                "wraps after twelve")
    }
}
