@testable import Fichero
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.select-marquee-lasso` and
/// `segment-editor.select-shift-toggles`. A band or a lasso selects the segments MOSTLY inside it, at the level being
/// edited (lines; regions with ⌘); ⇧-click on a selected segment removes it rather than starting a move; ⌘⇧A selects
/// the same kind. What breaks without these: a band that grabs every region it grazes, a lasso that cannot be drawn,
/// or a ⇧-click that cannot take one segment out of a selection.
@Suite(.tags(.paleography))
struct SegmentSelectionGesturesTests {
    typealias Gestures = SegmentSelectionGestures
    private let page: [Gestures.Box] = [
        .init(index: 0, bbox: [0.0, 0.0, 1.0, 1.0], level: "region"),
        .init(index: 1, bbox: [0.1, 0.1, 0.4, 0.05], level: "line"),
        .init(index: 2, bbox: [0.1, 0.2, 0.4, 0.05], level: "line"),
        .init(index: 3, bbox: [0.1, 0.3, 0.4, 0.05], level: "line")
    ]

    @Test("a band selects the lines mostly inside it, not one it only grazes, and not the region around them")
    func bandIsOverHalfAtTheLineLevel() {
        let band = Gestures.loop(ofBand: [0.05, 0.05, 0.5, 0.26])  // all of lines 1 and 2, a sliver of 3
        let level = Gestures.level(of: page, commandHeld: false)
        #expect(level == "line")
        #expect(Gestures.inside(band, boxes: page, level: level) == [1, 2])
    }

    @Test("with ⌘ held the band selects regions")
    func commandSelectsRegions() {
        let level = Gestures.level(of: page, commandHeld: true)
        #expect(Gestures.inside(Gestures.loop(ofBand: [0, 0, 1, 1]), boxes: page, level: level) == [0])
    }

    @Test("a lasso, a drawn loop, selects what it mostly holds")
    func lasso() {
        // A triangle holding all of line 2 and the left part of line 3 (under half of it).
        let loop: [[Double]] = [[0.0, 0.15], [0.9, 0.15], [0.0, 0.4]]
        #expect(Gestures.inside(loop, boxes: page, level: "line") == [2])
        #expect(Gestures.inside([[0, 0], [1, 1]], boxes: page, level: nil).isEmpty, "two points are not a loop")
    }

    @Test("a page with no lines selects whatever is shown")
    func noLines() {
        let regions = [Gestures.Box(index: 0, bbox: [0.1, 0.1, 0.2, 0.2], level: "region")]
        #expect(Gestures.level(of: regions, commandHeld: false) == nil)
    }

    @Test("⇧-click on a selected segment does not start a move, so it removes it from the selection")
    func shiftClickRemoves() {
        #expect(SegmentEditingMode.pressStartsMove(isEditing: true, onSelectedBox: true, shift: false))
        #expect(!SegmentEditingMode.pressStartsMove(isEditing: true, onSelectedBox: true, shift: true))
        let selection = RegionSelection()
        selection.select(1, artifactId: "a", documentId: "p")
        selection.toggle(2, artifactId: "a", documentId: "p")
        selection.toggle(1, artifactId: "a", documentId: "p")
        #expect(!selection.isSelected(1, in: "a"))
        #expect(selection.isSelected(2, in: "a"))
    }

    @Test("⌘⇧A selects every segment of a kind the selection holds")
    func sameKind() {
        let kinds: [String?] = ["region", "line", "line", "marginalia", nil]
        #expect(Gestures.sameKind(as: [1], kinds: kinds) == [1, 2])
        #expect(Gestures.sameKind(as: [0, 3], kinds: kinds) == [0, 3])
        #expect(Gestures.sameKind(as: [], kinds: kinds).isEmpty)
        #expect(Gestures.sameKind(as: [4], kinds: kinds).isEmpty)
    }
}
