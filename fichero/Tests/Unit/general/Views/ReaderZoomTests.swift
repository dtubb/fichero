@testable import Fichero
import Testing

#if os(macOS)
/// Reader zoom reflows (#5203, Daniel on the calfa chinese-vertical page: zooming pushed the page past the
/// column and the pane scrolled sideways). A pinch went to WebKit's `magnification`, which scales without
/// reflowing; it now moves the Reader's ONE zoom, `pageZoom`, which reflows. What breaks without these: a
/// pinch runs away past the zoom's range, or shrinks when the fingers spread.
struct ReaderZoomTests {
    @Test("a pinch scales the zoom the way the fingers go, and stays in the Reader's range")
    func pinch() {
        #expect(ReaderZoom.pinched(1.0, by: 0.1) > 1.0, "spreading zooms in")
        #expect(ReaderZoom.pinched(1.0, by: -0.1) < 1.0, "pinching zooms out")
        #expect(ReaderZoom.pinched(2.9, by: 0.5) == ReaderZoom.range.upperBound)
        #expect(ReaderZoom.pinched(0.6, by: -0.9) == ReaderZoom.range.lowerBound)
        #expect(ReaderZoom.pinched(1.0, by: 0) == 1.0)
    }

    @Test("the Lines view's pinch scales from where the gesture began, in the same range (reader.lines.pinch-zooms, #6428)")
    func linesPinch() {
        #expect(ReaderZoom.scaled(from: 1.0, by: 1.0) == 1.0)
        #expect(ReaderZoom.scaled(from: 1.0, by: 1.5) == 1.5, "a spread of 1.5x from 100% is 150%")
        #expect(ReaderZoom.scaled(from: 2.0, by: 0.5) == 1.0, "the running scale is from the start, not from the last step")
        #expect(ReaderZoom.scaled(from: 2.0, by: 3.0) == ReaderZoom.range.upperBound)
        #expect(ReaderZoom.scaled(from: 1.0, by: 0.1) == ReaderZoom.range.lowerBound)
    }
}
#endif
