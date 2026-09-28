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
}
#endif
