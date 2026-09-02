import SwiftUI

// Per-step settings editors and the "Add Step" section for ImageEditChainPanel.
// Split out of ImageEditChainPanel to keep the type/file under the SwiftLint
// thresholds.
extension ImageEditChainPanel {
    /// Commit a step's edited settings.
    ///
    /// In place when the host wired `onUpdateStep`: the step keeps its
    /// position and the engine re-renders the chain from that point, which is
    /// what "re-open a step and change it" has to mean. Otherwise it falls
    /// back to the older remove-then-re-add, which appends the replacement at
    /// the END of the chain — correct only for a step that was already last.
    func reapplyStep(at index: Int, params: [String: Any], legacy: () -> Void) {
        if let onUpdateStep {
            onUpdateStep(index, params)
        } else {
            onRemove(index)
            legacy()
        }
        selectedStepIndex = nil
    }

    /// True when re-editing keeps the step where it is. Drives the row's
    /// wording so the button never promises order it cannot keep.
    var editsStepsInPlace: Bool { onUpdateStep != nil }

    @ViewBuilder
    func stepEditor(for operation: ImageEditOperation, at index: Int) -> some View {
        switch operation.opKind {
        case "enhance":
            enhanceStepEditor(at: index)
        case "rotate":
            rotateStepEditor(at: index)
        case "straighten":
            straightenStepEditor(at: index)
        case "crop":
            cropStepEditor(for: operation, at: index)
        case "remove_background":
            removeBackgroundStepEditor(at: index)
        case "fuzzy_clean":
            fuzzyCleanStepEditor(at: index)
        case "segment":
            segmentStepEditor(at: index)
        default:
            HStack {
                Image(systemName: "info.circle").foregroundStyle(.secondary)
                Text("Remove and re-add to change settings.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private func enhanceStepEditor(at index: Int) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            enhanceSlider("Brightness", value: $enhanceBrightness)
            enhanceSlider("Contrast", value: $enhanceContrast)
            enhanceSlider("Sharpen", value: $enhanceSharpen)
            Toggle("Auto Levels", isOn: $enhanceAutoLevels).font(.caption)
            HStack {
                Spacer()
                Button(editsStepsInPlace ? "Update Step" : "Re-apply") {
                    reapplyStep(
                        at: index,
                        params: [
                            "brightness": enhanceBrightness,
                            "contrast": enhanceContrast,
                            "sharpen": enhanceSharpen,
                            "auto_levels": enhanceAutoLevels
                        ]
                    ) {
                        onEnhance(enhanceBrightness, enhanceContrast, enhanceSharpen, enhanceAutoLevels)
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(isBusy)
            }
        }
        .font(.caption)
    }

    @ViewBuilder
    private func rotateStepEditor(at index: Int) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text("Angle")
                    Spacer()
                    Text("\(Int(rotateAngle))°").monospacedDigit().foregroundStyle(.secondary)
                }
                Slider(value: $rotateAngle, in: -180...180, step: 1)
            }
            HStack(spacing: 8) {
                Button("0°") { rotateAngle = 0 }.buttonStyle(.bordered).controlSize(.mini)
                Button("90°") { rotateAngle = 90 }.buttonStyle(.bordered).controlSize(.mini)
                Button("−90°") { rotateAngle = -90 }.buttonStyle(.bordered).controlSize(.mini)
                Spacer()
                Button(editsStepsInPlace ? "Update Step" : "Re-apply") {
                    reapplyStep(at: index, params: ["angle": rotateAngle]) {
                        onRotate(rotateAngle)
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(isBusy)
            }
        }
        .font(.caption)
    }

    @ViewBuilder
    private func straightenStepEditor(at index: Int) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "crop.rotate")
                    .foregroundStyle(.secondary)
                Text("Auto-straighten — re-apply to rerun on the current image.")
                    .font(.caption2).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack {
                Spacer()
                Button("Re-apply") {
                    reapplyStep(at: index, params: [:]) { onStraighten() }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(isBusy)
            }
        }
    }

    @ViewBuilder
    private func cropStepEditor(for operation: ImageEditOperation, at index: Int) -> some View {
        // Same free-form-JSON hazard as the sliders: a crop written by one
        // path arrives as Int, by another as Double, and a bare `as? Int`
        // showed the user a 0×0 crop it could not then re-apply.
        let cropLeft = Int(Self.numericParam(operation.params, "left") ?? 0)
        let cropTop = Int(Self.numericParam(operation.params, "top") ?? 0)
        let cropWidth = Int(Self.numericParam(operation.params, "width") ?? 0)
        let cropHeight = Int(Self.numericParam(operation.params, "height") ?? 0)
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Image(systemName: "crop").foregroundStyle(.secondary)
                Text("\(cropWidth)×\(cropHeight) px")
                    .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                Text("at \(cropLeft),\(cropTop)")
                    .font(.caption2).foregroundStyle(.tertiary)
            }
            Text("Aspect ratio presets:")
                .font(.caption2).foregroundStyle(.tertiary)
            HStack(spacing: 6) {
                ForEach([("1:1", 1.0), ("4:3", 4.0/3.0), ("3:2", 1.5), ("16:9", 16.0/9.0)],
                        id: \.0) { label, ratio in
                    Button(label) {
                        let newWidth: Int
                        let newHeight: Int
                        if cropHeight > 0 && Double(cropWidth) / Double(cropHeight) > ratio {
                            newHeight = cropHeight
                            newWidth = Int(Double(cropHeight) * ratio)
                        } else {
                            newWidth = cropWidth
                            newHeight = cropWidth > 0 ? Int(Double(cropWidth) / ratio) : 0
                        }
                        let newLeft = cropLeft + (cropWidth - newWidth) / 2
                        let newTop = cropTop + (cropHeight - newHeight) / 2
                        reapplyStep(
                            at: index,
                            params: [
                                "left": newLeft,
                                "top": newTop,
                                "width": newWidth,
                                "height": newHeight
                            ]
                        ) {
                            onCrop(newLeft, newTop, newWidth, newHeight)
                        }
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.mini)
                    .disabled(isBusy || cropWidth == 0 || cropHeight == 0)
                }
            }
            Text("Or use the canvas marquee to free-crop.")
                .font(.caption2).foregroundStyle(.tertiary)
        }
    }

    @ViewBuilder
    private func removeBackgroundStepEditor(at index: Int) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "person.and.background.dotted")
                    .foregroundStyle(.secondary)
                Text("AI background removal — re-apply to rerun on the current image.")
                    .font(.caption2).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack {
                Spacer()
                Button("Re-apply") {
                    reapplyStep(at: index, params: [:]) { onRemoveBackground() }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(isBusy)
            }
        }
    }

    @ViewBuilder
    private func fuzzyCleanStepEditor(at index: Int) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "sparkles")
                    .foregroundStyle(.secondary)
                Text("Despeckle — removes noise and speckle artifacts; re-apply to rerun on the current image.")
                    .font(.caption2).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack {
                Spacer()
                Button("Re-apply") {
                    reapplyStep(at: index, params: [:]) { onFuzzyClean() }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(isBusy)
            }
        }
    }

    @ViewBuilder
    private func segmentStepEditor(at index: Int) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "square.split.2x1")
                    .foregroundStyle(.secondary)
                Text("Region segmentation — re-apply to rerun on the current image.")
                    .font(.caption2).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack {
                Spacer()
                Button("Re-apply") {
                    reapplyStep(at: index, params: [:]) { onSegment() }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(isBusy)
            }
        }
    }

    /// One saved parameter as a `Double`, whatever JSON shape it came back in.
    ///
    /// A chain is stored as free-form JSON, so a brightness the user set to
    /// exactly 1 round-trips as an Int and a bare `as? Double` misses it —
    /// which silently re-seeded the slider to its neutral default and made a
    /// re-opened step lie about its own settings.
    static func numericParam(_ params: [String: Any], _ key: String) -> Double? {
        if let value = params[key] as? Double { return value }
        if let value = params[key] as? Int { return Double(value) }
        if let value = params[key] as? NSNumber { return value.doubleValue }
        if let value = params[key] as? String { return Double(value) }
        return nil
    }

    func seedEnhanceSliders(from operation: ImageEditOperation) {
        guard operation.opKind == "enhance" else { return }
        enhanceBrightness = Self.numericParam(operation.params, "brightness") ?? 1.0
        enhanceContrast = Self.numericParam(operation.params, "contrast") ?? 1.0
        enhanceSharpen = Self.numericParam(operation.params, "sharpen") ?? 1.0
        enhanceAutoLevels = (operation.params["auto_levels"] as? Bool) ?? false
    }

    func seedRotateSlider(from operation: ImageEditOperation) {
        guard operation.opKind == "rotate" else { return }
        rotateAngle = Self.numericParam(operation.params, "angle") ?? 0
    }

    // MARK: - Add Step

    @ViewBuilder
    var addStepSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button {
                withAnimation(.easeInOut(duration: 0.12)) { addStepExpanded.toggle() }
            } label: {
                HStack {
                    Label("Add Step", systemImage: "plus.circle")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(Color.accentColor)
                    Spacer()
                    Image(systemName: addStepExpanded ? "chevron.up" : "chevron.down")
                        .font(.caption2).foregroundStyle(.secondary)
                }
                .padding(.horizontal, 12)
                .frame(height: 40)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            if addStepExpanded {
                addStepGrid.padding(.horizontal, 12).padding(.bottom, 12)
            }
        }
    }

    private var addStepGrid: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                addToolButton("rotate.left", title: "Rotate ↺") {
                    onRotate(90); addStepExpanded = false
                }
                addToolButton("rotate.right", title: "Rotate ↻") {
                    onRotate(-90); addStepExpanded = false
                }
                addToolButton("crop.rotate", title: "Straighten") {
                    onStraighten(); addStepExpanded = false
                }
            }
            DisclosureGroup {
                VStack(alignment: .leading, spacing: 8) {
                    enhanceSlider("Brightness", value: $enhanceBrightness)
                    enhanceSlider("Contrast", value: $enhanceContrast)
                    enhanceSlider("Sharpen", value: $enhanceSharpen)
                    Toggle("Auto Levels", isOn: $enhanceAutoLevels).font(.caption)
                    HStack {
                        Spacer()
                        Button("Apply Enhance") {
                            onEnhance(enhanceBrightness, enhanceContrast, enhanceSharpen, enhanceAutoLevels)
                            resetEnhanceSliders()
                            addStepExpanded = false
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                        .disabled(isBusy)
                    }
                }
                .font(.caption)
                .padding(.vertical, 6)
            } label: {
                HStack {
                    Image(systemName: "slider.horizontal.3").frame(width: 20).foregroundStyle(.secondary)
                    Text("Enhance").font(.subheadline)
                }
            }
            HStack(spacing: 8) {
                addToolButton("person.and.background.dotted", title: "Remove BG") {
                    onRemoveBackground(); addStepExpanded = false
                }
                addToolButton("sparkles", title: "Despeckle") {
                    onFuzzyClean(); addStepExpanded = false
                }
            }
            addToolButton("square.split.2x1", title: "Segment") {
                onSegment(); addStepExpanded = false
            }
            .frame(maxWidth: .infinity)
        }
    }

    private func addToolButton(_ icon: String, title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: icon).font(.caption).frame(maxWidth: .infinity)
        }
        .buttonStyle(.bordered)
        .controlSize(.small)
        .disabled(isBusy)
    }

    // MARK: - Shared Slider

    private func enhanceSlider(_ label: String, value: Binding<Double>) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(label)
                Spacer()
                Text(String(format: "%.2f×", value.wrappedValue)).monospacedDigit().foregroundStyle(.secondary)
            }
            Slider(value: value, in: 0.0...2.0)
        }
    }

    private func resetEnhanceSliders() {
        enhanceBrightness = 1.0; enhanceContrast = 1.0; enhanceSharpen = 1.0; enhanceAutoLevels = false
    }
}
