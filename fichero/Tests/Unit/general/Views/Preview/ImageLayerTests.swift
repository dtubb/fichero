@testable import Fichero
import Testing

/// The image layer (ruled 2026-09-27, Q2). What breaks without these: an "image off" that hides
/// the view instead of its pixels takes the overlays' frame and the region layer's clicks with it.
struct ImageLayerTests {
    @Test("off draws no pixels; on draws them fully")
    func alphaFollowsTheSwitch() {
        #expect(ImageLayer.alpha(visible: false) == 0)
        #expect(ImageLayer.alpha(visible: true) == 1)
    }

    @Test("the switch has one key, so every image canvas and the menu agree")
    func oneDefaultsKey() {
        #expect(ImageLayer.defaultsKey == "imagePreview.imageVisible")
    }
}
