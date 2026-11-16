#if canImport(AppKit)
import AppKit
@testable import Fichero
import Foundation
import Testing

/// A hovered or selected box takes its region's hue, and the region box lights with it (#6422,
/// `colour.selection-takes-its-region-hue`): what made the owner ask is a selection drawn in the accent on a page
/// whose boxes are coloured by region, so it said nothing about which region the line was in.
struct RegionHueSelectionTests {
    private let tone = RegionColours.Tone(hue: 3, strength: 0.4)

    @Test("a selection and a hover are their region's hue at full strength; dimmed in a window not in front")
    func selectionTakesTheRegionHue() {
        let hue = SelectionStyle.regionPalette[3]
        #expect(SelectionStyle.stroke(tone, emphasized: true) == hue, "never shaded along the order")
        #expect(SelectionStyle.wash(tone, emphasized: true) == hue.withAlphaComponent(SelectionStyle.washAlpha(emphasized: true)))
        let dim = SelectionStyle.stroke(tone, emphasized: false)
        #expect(dim != hue && dim != SelectionStyle.stroke(emphasized: false), "the hue desaturated, never grey or the accent")
        #expect(SelectionStyle.hover(tone) == hue)
    }

    @Test("a box with no region keeps the accent")
    func noRegionKeepsTheAccent() {
        #expect(SelectionStyle.stroke(nil, emphasized: true) == NSColor.controlAccentColor)
        #expect(SelectionStyle.hover(nil) == SelectionStyle.hoverBase)
    }

    private var overlay: DocumentOverlay {
        var overlay = DocumentOverlay()
        overlay.boxes = [
            .init(bbox: [0, 0, 1, 0.5], confidence: nil, segmentId: "r1", kind: "region", tone: .init(hue: 3, strength: 1)),
            .init(bbox: [0, 0, 1, 0.1], confidence: nil, segmentId: "l1", kind: "line", parentSegmentId: "r1", tone: tone),
            .init(bbox: [0, 0.1, 1, 0.1], confidence: nil, segmentId: "l2", kind: "line", parentSegmentId: "r1", tone: tone),
            .init(bbox: [0, 0.6, 1, 0.1], confidence: nil, segmentId: "loose", kind: "line")
        ]
        return overlay
    }

    @Test("a hovered or selected line lights its region once; a region or a loose line lights nothing")
    func theRegionLightsWithItsLine() {
        #expect(overlay.litRegions(for: ["l1", "l2"]).map(\.segmentId) == ["r1"])
        #expect(overlay.litRegions(for: ["r1"]).isEmpty)
        #expect(overlay.litRegions(for: ["loose"]).isEmpty)
        #expect(overlay.litRegions(for: []).isEmpty)
    }

    @Test("each selected rect has its box's tone, in the order drawn; one no box is drawn at has none")
    func selectedRectsCarryTheirTone() {
        var overlay = overlay
        overlay.selected = [[0, 0, 1, 0.1], [0, 0.6, 1, 0.1], [0.2, 0.2, 0.1, 0.1]]
        let image = CGRect(x: 0, y: 0, width: 1000, height: 1000)
        #expect(overlay.selectedTones(in: image, imageRect: image) == [tone, nil, nil])
    }
}
#endif
