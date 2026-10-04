#if canImport(AppKit)
import AppKit
@testable import Fichero
import SwiftUI
import Testing

/// #5411, the chinese-vertical page in the Preview with Show Text Inline on: every column's reading was
/// one horizontal string, the region's reading (every line joined) was drawn page-tall and ran off the
/// page, resting on a line highlighted the region around it, and the magnifier strip lay across the
/// columns. What breaks without these: a vertical line's reading is set sideways again, a reading runs
/// past its box, the hover names the region instead of the line, or the strip shows a slice across many
/// lines instead of a stretch of one, or the person's own choice of side or bottom is overridden or
/// forgotten.
struct PreviewVerticalPageTests {
    /// A stand-in measure that makes the fitting exact: a grapheme is one `size` wide, a row 1.2 `size`
    /// tall. The Unicode isolates `SegmentLabel` wraps a horizontal reading in take no room.
    private let measure: (String, CGFloat) -> CGSize = { text, size in
        let isolates: Set<Character> = ["\u{2066}", "\u{2067}", "\u{2068}", "\u{2069}"]
        let rows = text.split(separator: "\n", omittingEmptySubsequences: false)
        let widest = rows.map { $0.filter { !isolates.contains($0) }.count }.max() ?? 0
        return CGSize(width: CGFloat(widest) * size, height: CGFloat(rows.count) * size * 1.2)
    }

    // MARK: source.editor.inline-text-in-its-direction

    @Test("inline-text-in-its-direction: a ttb line is a column of its graphemes inside its own box")
    func verticalLineIsAColumn() {
        let column = CGRect(x: 300, y: 100, width: 20, height: 200)
        let layout = InlineWords.layout("公政三十一", direction: "ttb", in: column, measure: measure)
        #expect(layout.vertical)
        #expect(layout.text == "公\n政\n三\n十\n一", "read top to bottom, one grapheme per row")
        #expect(layout.frame.height > layout.frame.width, "a column, not a row")
        #expect(column.contains(layout.frame), "inside its own box")
        #expect(abs(layout.frame.midX - column.midX) < 0.001, "centred across the column")
    }

    @Test("inline-text-in-its-direction: a horizontal line stays one row, an rtl one set from the right")
    func horizontalLinesStayRows() {
        let row = CGRect(x: 0, y: 0, width: 300, height: 20)
        let ltr = InlineWords.layout("ok", direction: "ltr", in: row, measure: measure)
        #expect(!ltr.vertical)
        #expect(ltr.frame.minX == row.minX)
        let rtl = InlineWords.layout("ܚܨܪܘܢ", direction: "rtl", in: row, measure: measure)
        #expect(rtl.rightToLeft)
        #expect(abs(rtl.frame.maxX - row.maxX) < 0.001)
    }

    // MARK: source.editor.inline-text-fits-its-box

    @Test("inline-text-fits-its-box: a column too short for its reading shrinks to fit its height")
    func columnFitsItsHeight() {
        let short = CGRect(x: 0, y: 0, width: 20, height: 60)
        let layout = InlineWords.layout("公政三十一", direction: "ttb", in: short, measure: measure)
        #expect(short.contains(layout.frame))
        #expect(layout.fontSize < short.width * InlineWords.heightFill, "scaled down from the column's width")
    }

    @Test("inline-text-fits-its-box: a many-row reading never runs past its box, at any zoom")
    func manyRowsFit() {
        let joined = ["公政三十一", "卷第三十八", "政術部十二", "廉潔三十二"].joined(separator: "\n")
        for scale in [0.21, 0.47, 1.0, 2.0] as [CGFloat] {
            let box = CGRect(x: 0, y: 0, width: 500 * scale, height: 400 * scale)
            let layout = InlineWords.layout(joined, direction: nil, in: box, measure: measure)
            #expect(box.contains(layout.frame), "ran past its box at \(scale)")
        }
    }

    @Test("inline-text-fits-its-box: a short word still takes its box's height, a long one its width")
    func horizontalFitUnchanged() {
        let box = CGRect(x: 0, y: 0, width: 100, height: 20)
        #expect(InlineWords.fittedSize("ok", in: box, measure: measure) == box.height * InlineWords.heightFill)
        let long = String(repeating: "m", count: 30)
        #expect(measure(long, InlineWords.fittedSize(long, in: box, measure: measure)).width <= box.width)
    }

    @Test("inline-text-fits-its-box: a region under lines sets no text; alone, or a line, it does")
    func regionUnderLinesSetsNoText() {
        #expect(!DocumentOverlay.setsTextInline(kind: "region", linesShown: true))
        #expect(DocumentOverlay.setsTextInline(kind: "line", linesShown: true))
        #expect(DocumentOverlay.setsTextInline(kind: "region", linesShown: false))
        #expect(DocumentOverlay.setsTextInline(kind: "word", linesShown: false))
    }

    // MARK: source.editor.hover-picks-the-line

    @Test("hover-picks-the-line: the smallest box under the pointer wins, whatever the drawing order")
    func hoverPicksTheLine() {
        let region = CGRect(x: 0, y: 0, width: 100, height: 100)
        let line = CGRect(x: 10, y: 10, width: 10, height: 80)
        #expect(DocumentOverlay.smallestContaining(CGPoint(x: 15, y: 50), in: [region, line]) == 1)
        #expect(DocumentOverlay.smallestContaining(CGPoint(x: 15, y: 50), in: [line, region]) == 0)
        #expect(DocumentOverlay.smallestContaining(CGPoint(x: 60, y: 50), in: [region, line]) == 0,
                "in the region outside every line: the region")
        #expect(DocumentOverlay.smallestContaining(CGPoint(x: 200, y: 50), in: [region, line]) == nil)
    }

    // MARK: magnifier.strip-follows-line-direction

    @Test("strip-follows-line-direction: vertical lines turn the strip vertical; anything else stays horizontal")
    func stripFollowsTheLines() {
        #expect(MagnifierStrip.axis(forLineDirections: ["ttb", "ttb", "ltr"]) == .vertical)
        #expect(MagnifierStrip.axis(forLineDirections: ["btt"]) == .vertical)
        #expect(MagnifierStrip.axis(forLineDirections: ["ltr", "rtl"]) == .horizontal)
        #expect(MagnifierStrip.axis(forLineDirections: ["ttb", "ltr"]) == .horizontal, "a tie stays as it was")
        #expect(MagnifierStrip.axis(forLineDirections: []) == .horizontal, "no direction known")
    }

    // MARK: magnifier.strip-placement-is-the-persons

    @Test("strip-placement-is-the-persons: an explicit choice wins over the lines; Automatic follows them")
    func choiceOverridesTheDefault() {
        let vertical = ["ttb", "ttb"], horizontal = ["ltr"]
        #expect(MagnifierStrip.axis(placement: .bottom, lineDirections: vertical) == .horizontal)
        #expect(MagnifierStrip.axis(placement: .side, lineDirections: horizontal) == .vertical)
        #expect(MagnifierStrip.axis(placement: .automatic, lineDirections: vertical) == .vertical)
        #expect(MagnifierStrip.axis(placement: .automatic, lineDirections: horizontal) == .horizontal)
    }

    /// The choice is kept as the pane option `MagnifierStrip.placementKey` (`@PaneStorage`): what one pane
    /// chose reads back for that pane, and does not change another's. Driven through `PaneScopedOption`,
    /// the read and write rules `@PaneStorage` applies (its hosted round trip is
    /// `LibraryOptionsPerPaneTests`).
    @Test("strip-placement-is-the-persons: each pane remembers its own choice, as stored")
    func choicePersistsPerPane() {
        let left = UUID(), right = UUID()
        var map = "{}"
        map = PaneScopedOption.setting(MagnifierStrip.Placement.side.rawValue, in: map, pane: left)
        map = PaneScopedOption.setting(MagnifierStrip.Placement.bottom.rawValue, in: map, pane: right)
        let shared = MagnifierStrip.Placement.automatic.rawValue
        #expect(MagnifierStrip.Placement(stored: PaneScopedOption.value(map, pane: left, shared: shared)) == .side)
        #expect(MagnifierStrip.Placement(stored: PaneScopedOption.value(map, pane: right, shared: shared)) == .bottom)
        #expect(MagnifierStrip.Placement(stored: PaneScopedOption.value(map, pane: UUID(), shared: shared)) == .automatic,
                "a pane that never chose takes the shared value")
        #expect(MagnifierStrip.Placement(stored: "") == .automatic, "nothing stored is Automatic")
        #expect(MagnifierStrip.placementKey == "imagePreview.magnifierStripPlacement", "renaming the key forgets every choice")
    }
}
#endif
