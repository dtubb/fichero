import SwiftUI

// Per-step settings editors and the "Add Step" section for ImageEditChainPanel.
// Split out of ImageEditChainPanel to keep the type/file under the SwiftLint
// thresholds.
extension ImageEditChainPanel {
    @ViewBuilder
    // swiftlint:disable:next function_body_length
    func stepEditor(for operation: ImageEditOperation, at index: Int) -> some View {
        switch operation.opKind {
        case "enhance":
            VStack(alignment: .leading, spacing: 8) {
                enhanceSlider("Brightness", value: $enhanceBrightness)
                enhanceSlider("Contrast", value: $enhanceContrast)
                enhanceSlider("Sharpen", value: $enhanceSharpen)
                Toggle("Auto Levels", isOn: $enhanceAutoLevels).font(.caption)
                HStack {
                    Spacer()
                    Button("Re-apply") {
                        onRemove(index)
                        onEnhance(enhanceBrightness, enhanceContrast, enhanceSharpen, enhanceAutoLevels)
                        selectedStepIndex = nil
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .disabled(isBusy)
                }
            }
            .font(.caption)
        case "rotate":
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
                    Button("Re-apply") {
                        onRemove(index)
                        onRotate(rotateAngle)
                        selectedStepIndex = nil
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .disabled(isBusy)
                }
            }
            .font(.caption)
        case "straighten":
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
                        onRemove(index)
                        onStraighten()
                        selectedStepIndex = nil
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .disabled(isBusy)
                }
            }
        case "crop":
            let cropLeft = operation.params["left"] as? Int ?? 0
            let cropTop = operation.params["top"] as? Int ?? 0
            let cropWidth = operation.params["width"] as? Int ?? 0
            let cropHeight = operation.params["height"] as? Int ?? 0
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
                            onRemove(index)
                            onCrop(newLeft, newTop, newWidth, newHeight)
                            selectedStepIndex = nil
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.mini)
                        .disabled(isBusy || cropWidth == 0 || cropHeight == 0)
                    }
                }
                Text("Or use the canvas marquee to free-crop.")
                    .font(.caption2).foregroundStyle(.tertiary)
            }
        case "remove_background":
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
                        onRemove(index)
                        onRemoveBackground()
                        selectedStepIndex = nil
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .disabled(isBusy)
                }
            }
        case "fuzzy_clean":
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
                        onRemove(index)
                        onFuzzyClean()
                        selectedStepIndex = nil
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .disabled(isBusy)
                }
            }
        case "segment":
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
                        onRemove(index)
                        onSegment()
                        selectedStepIndex = nil
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .disabled(isBusy)
                }
            }
        default:
            HStack {
                Image(systemName: "info.circle").foregroundStyle(.secondary)
                Text("Remove and re-add to change settings.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    func seedEnhanceSliders(from operation: ImageEditOperation) {
        guard operation.opKind == "enhance" else { return }
        enhanceBrightness = (operation.params["brightness"] as? Double) ?? 1.0
        enhanceContrast = (operation.params["contrast"] as? Double) ?? 1.0
        enhanceSharpen = (operation.params["sharpen"] as? Double) ?? 1.0
        enhanceAutoLevels = (operation.params["auto_levels"] as? Bool) ?? false
    }

    func seedRotateSlider(from operation: ImageEditOperation) {
        guard operation.opKind == "rotate" else { return }
        rotateAngle = (operation.params["angle"] as? Double)
            ?? Double(operation.params["angle"] as? Int ?? 0)
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
