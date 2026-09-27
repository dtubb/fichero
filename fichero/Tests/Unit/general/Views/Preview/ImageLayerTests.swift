@testable import Fichero
import Testing

/// The image layer (ruled 2026-09-27, Q2). "Image off" stops drawing the PIXELS; the view stays,
/// because the document overlay lives inside it.
struct ImageLayerTests {
    @Test("the switch has one key, so every image canvas and the menu agree")
    func oneDefaultsKey() {
        #expect(ImageLayer.defaultsKey == "imagePreview.imageVisible")
    }

    // MARK: - Workspace defaults (Q2: each layer's default is tied to the workspace)

    @Test("a layer starts where the workspace says, else where it was left")
    func startsAtTheWorkspaceValue() {
        #expect(PreviewLayerDefaults.start(workspace: false, remembered: true) == false)
        #expect(PreviewLayerDefaults.start(workspace: true, remembered: false) == true)
        #expect(PreviewLayerDefaults.start(workspace: nil, remembered: false) == false)
    }

    /// Opening a workspace must not change what every OTHER pane opens with: a pane that started
    /// at its workspace's value did not choose it. What breaks without this: open Transcribe once
    /// (word boxes on) and every plain preview after it inherits Transcribe's layers.
    @Test("only a person's move away from the workspace value is remembered")
    func workspaceValuesAreNotRemembered() {
        #expect(!PreviewLayerDefaults.shouldRemember(true, workspace: true))
        #expect(PreviewLayerDefaults.shouldRemember(false, workspace: true))
        #expect(PreviewLayerDefaults.shouldRemember(true, workspace: nil))
    }
}
