@testable import Fichero
import Testing

/// #6725 (owner 2026-11-18): with the Display switches off, every box and the reading order still showed.
/// Each switch hides only its own layer, both ways.
struct OverlaySwitchesTests {
    @Test("source.editor.switch.bounding-box: Show Bounding Box off hides every segment rectangle, plain boxes included")
    func boundingBoxSwitch() {
        var overlay = DocumentOverlay()
        overlay.showsBoundingBoxes = true
        #expect(overlay.drawsRectangles)
        overlay.showsBoundingBoxes = false
        #expect(!overlay.drawsRectangles)
    }
}
