@testable import Fichero
import Testing

/// #6457: Up/Down move the segment selection through the page in reading order; Shift extends; nothing wraps.
@Suite("Up and Down move the segment selection (#6457)")
struct SegmentSelectionStepTests {
    private let order = ["a", "b", "c", "d"]

    @Test("Down selects the next segment, Up the previous")
    func movesOnePlace() {
        #expect(InspectorPath.stepped(["b"], in: order, by: 1, extend: false) == ["c"])
        #expect(InspectorPath.stepped(["b"], in: order, by: -1, extend: false) == ["a"])
    }

    @Test("from several selected, Down goes past the last and Up before the first")
    func fromSeveral() {
        #expect(InspectorPath.stepped(["b", "c"], in: order, by: 1, extend: false) == ["d"])
        #expect(InspectorPath.stepped(["c", "b"], in: order, by: -1, extend: false) == ["a"])
    }

    @Test("Shift adds the next segment beyond the far end")
    func shiftExtends() {
        #expect(InspectorPath.stepped(["b"], in: order, by: 1, extend: true) == ["b", "c"])
        #expect(InspectorPath.stepped(["b", "c"], in: order, by: -1, extend: true) == ["a", "b", "c"])
    }

    @Test("at the edge nothing moves and nothing wraps, so the key keeps its other job")
    func noWrap() {
        #expect(InspectorPath.stepped(["d"], in: order, by: 1, extend: false) == nil)
        #expect(InspectorPath.stepped(["a"], in: order, by: -1, extend: true) == nil)
        #expect(InspectorPath.stepped(["a"], in: [], by: 1, extend: false) == nil)
        #expect(InspectorPath.stepped(["zz"], in: order, by: 1, extend: false) == nil)
    }

    @Test("with nothing selected the keys start the selection where the surface asks: Down the first, Up the last (#6474)")
    func startsFromNothing() {
        #expect(InspectorPath.stepped([], in: order, by: 1, extend: false, startsFromNothing: true) == ["a"])
        #expect(InspectorPath.stepped([], in: order, by: -1, extend: false, startsFromNothing: true) == ["d"])
        #expect(InspectorPath.stepped([], in: order, by: 1, extend: true, startsFromNothing: true) == ["a"])
    }

    @Test("a surface whose arrows pan or page (the Preview) is left alone with nothing selected")
    func theDefaultLeavesTheKeyToThePreview() {
        #expect(InspectorPath.stepped([], in: order, by: 1, extend: false) == nil)
        #expect(InspectorPath.stepped([], in: order, by: -1, extend: false) == nil)
    }
}
