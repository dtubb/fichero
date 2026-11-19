@testable import Fichero
import Foundation
import Testing

/// `source.editor.switches-hide-their-own-layer` (#6725, owner 2026-11-18): with the Display switches off, every box
/// and the reading order still showed. Each switch hides only its own layer, both ways.
struct OverlaySwitchesTests {
    private let plain = DocumentOverlay.Box(bbox: [0.1, 0.1, 0.2, 0.1], confidence: 1)
    private let shaped = DocumentOverlay.Box(
        bbox: [0.5, 0.5, 0.2, 0.1], confidence: 1, shapes: [.polygon([[0.5, 0.5], [0.7, 0.5], [0.6, 0.6]])]
    )

    @Test("source.editor.switches-hide-their-own-layer: Show Bounding Box off draws no plain box; a shaped one keeps its shape")
    func boundingBoxSwitch() {
        var overlay = DocumentOverlay(boxes: [plain, shaped])
        overlay.showsBoundingBoxes = true
        #expect(overlay.boxes.filter { overlay.drawsRectangle(of: $0) }.count == 2)
        #expect(overlay.drawsRectangleBesideShapes)
        overlay.showsBoundingBoxes = false
        #expect(overlay.boxes.filter { overlay.drawsRectangle(of: $0) } == [shaped], "only the shape is left")
        #expect(!overlay.drawsRectangleBesideShapes)
    }

    @Test("source.editor.switches-hide-their-own-layer: a stored old Show Bounding Box off does not blank plain boxes")
    func oldStoredOffIsNotRead() {
        // The new switch is pane-only: a pane with no entry takes its default, never the shared old value.
        let pane = UUID()
        #expect(PaneScopedOption.value("{}", pane: pane, shared: false, paneOnly: true))
        #expect(!PaneScopedOption.value(#"{"\#(pane.uuidString)":false}"#, pane: pane, shared: true, paneOnly: true),
                "a pane's own choice still holds")
    }

    @Test("source.editor.switches-hide-their-own-layer: Shade by Reading Order off draws every box at full strength, same hue")
    func shadeSwitch() {
        var box = plain
        box.tone = RegionColours.Tone(hue: 3, strength: 0.5)
        var overlay = DocumentOverlay(boxes: [box, plain])
        overlay.shadeBoxes(byOrder: true)
        #expect(overlay.boxes[0].tone == RegionColours.Tone(hue: 3, strength: 0.5))
        overlay.shadeBoxes(byOrder: false)
        #expect(overlay.boxes[0].tone == RegionColours.Tone(hue: 3, strength: 1))
        #expect(overlay.boxes[1].tone == nil, "an untoned box stays plain")
    }
}
