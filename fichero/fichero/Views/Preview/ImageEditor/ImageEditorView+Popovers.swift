import SwiftUI

extension ImageEditorView {
    // MARK: - Enhance popover

    var enhancePopover: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Enhance").font(.headline)
            enhanceSlider("Brightness", value: $brightness)
            enhanceSlider("Contrast", value: $contrast)
            enhanceSlider("Sharpen", value: $sharpen)
            HStack {
                Button("Auto Levels") {
                    enhanceCommitted = true
                    Task { await model.enhance(brightness: 1, contrast: 1, sharpen: 1, autoLevels: true) }
                    showEnhancePopover = false
                }
                Spacer()
                Button("Apply") {
                    enhanceCommitted = true
                    Task {
                        await model.enhance(
                            brightness: brightness,
                            contrast: contrast,
                            sharpen: sharpen,
                            autoLevels: false
                        )
                    }
                    resetEnhanceSliders()
                    showEnhancePopover = false
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(16)
        .frame(width: 260)
        // Live client-side preview while dragging (#3673): composite the slider
        // values over the original via Core Image — no backend — so the canvas
        // updates at 60fps. On commit (Apply/Auto-Levels) the server render
        // replaces it; on dismiss-without-commit the provisional frame is dropped.
        .onChange(of: brightness) { previewLiveEnhance() }
        .onChange(of: contrast) { previewLiveEnhance() }
        .onChange(of: sharpen) { previewLiveEnhance() }
        .onDisappear {
            if !enhanceCommitted { model.discardLiveEdit() }
            enhanceCommitted = false
        }
    }

    /// Push the current enhance-slider values to the model's client-side live
    /// preview (#3673) — provisional, replaced by the server render on commit.
    private func previewLiveEnhance() {
        model.previewLiveEdit(brightness: brightness, contrast: contrast, sharpen: sharpen)
    }

    // MARK: - Rotate popover (#3673)

    var rotatePopover: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Rotate").font(.headline)
            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text("Angle").font(.subheadline)
                    Spacer()
                    Text("\(Int(rotateAngle))°")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
                Slider(value: $rotateAngle, in: -180...180, step: 1)
            }
            HStack {
                Button("Reset") { rotateAngle = 0 }
                Spacer()
                Button("Apply") {
                    rotateCommitted = true
                    let angle = rotateAngle
                    Task { await model.rotate(by: angle) }
                    rotateAngle = 0
                    showRotatePopover = false
                }
                .keyboardShortcut(.defaultAction)
                .disabled(rotateAngle == 0)
            }
        }
        .padding(16)
        .frame(width: 260)
        // Live client-side preview while dragging (#3673): CIFilter.straighten
        // over the original — no backend — so the rotate previews at 60fps. On
        // Apply the server rotate op replaces it; on dismiss-without-commit the
        // provisional frame is dropped. Same pattern as the enhance sliders.
        .onChange(of: rotateAngle) { model.previewLiveEdit(angleDegrees: rotateAngle) }
        .onDisappear {
            if !rotateCommitted { model.discardLiveEdit() }
            rotateCommitted = false
        }
    }

    private func enhanceSlider(_ label: String, value: Binding<Double>) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(label).font(.subheadline)
                Spacer()
                Text(String(format: "%.2f×", value.wrappedValue))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            Slider(value: value, in: 0.0...2.0)
        }
    }

    private func resetEnhanceSliders() {
        brightness = 1.0
        contrast = 1.0
        sharpen = 1.0
    }
}
