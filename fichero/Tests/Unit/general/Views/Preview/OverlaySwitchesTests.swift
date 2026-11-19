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

extension OverlaySwitchesTests {
    @Test("source.editor.colour.shade-is-a-display-option: a pane's Shade by Reading Order off draws every line at full strength, same hue")
    func shadeSwitch() {
        let tone = RegionColours.Tone(hue: 3, strength: 0.5)
        #expect(tone.shaded(true) == tone)
        #expect(tone.shaded(false) == RegionColours.Tone(hue: 3, strength: 1))
    }
}
