@testable import Fichero
import Foundation
import Testing

/// The page's text readouts (#6422): Show Text on Hover is off by default and waits for the pointer to rest; Show Text
/// of the Selection labels the first few selected boxes with words.
struct HoverReadoutTests {
    private struct Box {
        let id: String?
        let text: String
    }

    @Test("the hover label shows only with the switch on and the pointer at rest where it is")
    func hoverWaitsForRest() {
        let here = CGPoint(x: 10, y: 20)
        #expect(!HoverReadout.showsHover(enabled: false, pointer: here, rested: here), "off by default")
        #expect(!HoverReadout.showsHover(enabled: true, pointer: here, rested: nil), "not before the pointer rests")
        #expect(!HoverReadout.showsHover(enabled: true, pointer: here, rested: CGPoint(x: 11, y: 20)), "it moved on")
        #expect(HoverReadout.showsHover(enabled: true, pointer: here, rested: here))
        #expect(!HoverReadout.showsHover(enabled: true, pointer: nil, rested: nil))
    }

    @Test("the selection's labels: with the switch on, the selected boxes with words, at most three, in drawn order")
    func selectionLabels() {
        let boxes = (1...5).map { Box(id: "l\($0)", text: $0 == 2 ? "" : "line \($0)") } + [Box(id: nil, text: "x")]
        let all: Set<String> = ["l1", "l2", "l3", "l4", "l5"]
        let shown = HoverReadout.labelledSelection(boxes, selected: all, enabled: true, id: \.id, text: \.text)
        #expect(shown.map(\.id) == ["l1", "l3", "l4"])
        #expect(HoverReadout.labelledSelection(boxes, selected: all, enabled: false, id: \.id, text: \.text).isEmpty)
        #expect(HoverReadout.labelledSelection(boxes, selected: [], enabled: true, id: \.id, text: \.text).isEmpty)
    }
}
