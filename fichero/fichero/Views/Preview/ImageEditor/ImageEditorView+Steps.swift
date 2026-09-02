import SwiftUI

extension ImageEditorView {
    /// The edit-steps stack, beside the canvas while you are editing.
    ///
    /// The list already existed, but only in the window Inspector's Edits tab
    /// — so the surface where you actually make edits never showed you the
    /// stack you were building (Daniel, 2026-09-02: he wants the Aperture /
    /// Lightroom behaviour, where the steps list IS the editor). It is not
    /// behind a toggle: while the image editor is open the stack is the point,
    /// and a switch for it would be exactly the needless toggle the
    /// dead-simple-UX rule forbids.
    ///
    /// This host is also the one that wires `onUpdateStep`, so re-opening a
    /// step here edits it IN PLACE and the chain re-renders from that step
    /// down, instead of the remove-then-append the unwired Inspector copy
    /// still falls back to.
    var stepsPanel: some View {
        ImageEditChainPanel(
            chain: model.chain,
            isBusy: model.isBusy,
            selectedStepIndex: Binding(
                get: { model.selectedStepIndex },
                set: { model.selectedStepIndex = $0 }
            ),
            onRemove: { index in Task { await model.removeOperation(at: index) } },
            onReset: { Task { await model.resetAll() } },
            onRotate: { angle in Task { await model.rotate(by: angle) } },
            onStraighten: { Task { await model.straighten() } },
            onEnhance: { brightness, contrast, sharpen, auto in
                Task {
                    await model.enhance(
                        brightness: brightness,
                        contrast: contrast,
                        sharpen: sharpen,
                        autoLevels: auto
                    )
                }
            },
            onCrop: { left, top, width, height in
                Task { await model.crop(left: left, top: top, width: width, height: height) }
            },
            onRemoveBackground: { Task { await model.removeBackground() } },
            onFuzzyClean: { Task { await model.fuzzyClean() } },
            onSegment: { Task { await model.segment() } },
            onUpdateStep: { index, params in
                Task { await model.updateOperation(at: index, params: params) }
            }
        )
        .frame(width: ImageEditorView.stepsPanelWidth)
        .accessibilityIdentifier("imageEditStepsPanel")
    }
}
