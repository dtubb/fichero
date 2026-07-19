import SwiftUI

// swiftlint:disable file_length

/// Photos-style edit chain panel (#1420).
///
/// Shows applied steps with expandable per-step settings (bidirectional
/// selection with the canvas via selectedStepIndex), plus an "Add Step"
/// collapsible section for all available tools.
struct ImageEditChainPanel: View {
    let chain: ImageEditChain
    let isBusy: Bool
    /// Bidirectional selection — inspector and canvas share this binding (#1420).
    @Binding var selectedStepIndex: Int?
    let onRemove: (Int) -> Void
    let onReset: () -> Void
    let onRotate: (Double) -> Void
    let onStraighten: () -> Void
    let onEnhance: (Double, Double, Double, Bool) -> Void
    /// Re-apply a crop at a new pixel rect (left, top, width, height). Called after
    /// onRemove so the chain has only one crop step at a time.
    let onCrop: (Int, Int, Int, Int) -> Void
    let onRemoveBackground: () -> Void
    let onFuzzyClean: () -> Void
    let onSegment: () -> Void

    @State private var addStepExpanded = false
    @State private var enhanceBrightness: Double = 1.0
    @State private var enhanceContrast: Double = 1.0
    @State private var enhanceSharpen: Double = 1.0
    @State private var enhanceAutoLevels = false
    @State private var rotateAngle: Double = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider()
            chainSection
            Divider()
            addStepSection
        }
        .background(Color(.windowBackgroundColor))
    }

    // MARK: - Header

    private var header: some View {
        HStack {
            Label("Edit Steps", systemImage: "slider.horizontal.3")
                .font(.headline)
            Spacer()
            if !chain.isEmpty {
                Text("\(chain.operations.count)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
                Button(role: .destructive, action: onReset) {
                    Image(systemName: "trash")
                }
                .buttonStyle(.borderless)
                .disabled(isBusy)
                .help("Reset all edits — restores the original image")
                .accessibilityIdentifier("imageEditChainReset")
            }
        }
        .padding(.horizontal, 12)
        // Match the shared pane top-toolbar height (#1449/#1460).
        .frame(height: MiniToolbar<EmptyView, EmptyView>.standardHeight)
    }

    // MARK: - Chain

    @ViewBuilder
    private var chainSection: some View {
        if chain.isEmpty {
            emptyChainState
        } else {
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(Array(chain.operations.enumerated()), id: \.element.id) { index, operation in
                        stepRow(index: index, operation: operation)
                        if index < chain.operations.count - 1 {
                            Divider().padding(.leading, 40)
                        }
                    }
                }
            }
            .frame(maxHeight: 280)
        }
    }

    private var emptyChainState: some View {
        VStack(spacing: 6) {
            Image(systemName: "wand.and.stars")
                .font(.title2)
                .foregroundStyle(.tertiary)
            Text("No edits applied yet")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text("Use \"Add Step\" below to start editing.")
                .font(.caption)
                .foregroundStyle(.tertiary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .padding(.horizontal, 12)
    }

    // MARK: - Step Row (expandable, bidirectional-selected)

    @ViewBuilder
    private func stepRow(index: Int, operation: ImageEditOperation) -> some View {
        let isSelected = selectedStepIndex == index
        VStack(alignment: .leading, spacing: 0) {
            Button {
                withAnimation(.easeInOut(duration: 0.12)) {
                    if isSelected {
                        selectedStepIndex = nil
                    } else {
                        selectedStepIndex = index
                        seedEnhanceSliders(from: operation)
                        seedRotateSlider(from: operation)
                    }
                }
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: operation.icon)
                        .frame(width: 22)
                        .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(operation.title).font(.subheadline)
                        if !operation.summary.isEmpty {
                            Text(operation.summary).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                    Image(systemName: isSelected ? "chevron.up" : "chevron.down")
                        .font(.caption2).foregroundStyle(.tertiary)
                    Button {
                        if selectedStepIndex == index { selectedStepIndex = nil }
                        onRemove(index)
                    } label: {
                        Image(systemName: "minus.circle")
                    }
                    .buttonStyle(.borderless)
                    .foregroundStyle(.secondary)
                    .disabled(isBusy)
                    .help("Remove this step")
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .contentShape(Rectangle())
                .background(isSelected ? Color.accentColor.opacity(0.06) : Color.clear)
            }
            .buttonStyle(.plain)

            if isSelected {
                stepEditor(for: operation, at: index)
                    .padding(.horizontal, 12)
                    .padding(.bottom, 10)
            }
        }
    }
}

// MARK: - Step Editor & Add Step

extension ImageEditChainPanel {
    @ViewBuilder
    // swiftlint:disable:next function_body_length
    private func stepEditor(for operation: ImageEditOperation, at index: Int) -> some View {
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

    private func seedEnhanceSliders(from operation: ImageEditOperation) {
        guard operation.opKind == "enhance" else { return }
        enhanceBrightness = (operation.params["brightness"] as? Double) ?? 1.0
        enhanceContrast = (operation.params["contrast"] as? Double) ?? 1.0
        enhanceSharpen = (operation.params["sharpen"] as? Double) ?? 1.0
        enhanceAutoLevels = (operation.params["auto_levels"] as? Bool) ?? false
    }

    private func seedRotateSlider(from operation: ImageEditOperation) {
        guard operation.opKind == "rotate" else { return }
        rotateAngle = (operation.params["angle"] as? Double)
            ?? Double(operation.params["angle"] as? Int ?? 0)
    }

    // MARK: - Add Step

    @ViewBuilder
    private var addStepSection: some View {
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

#Preview("With edits") {
    @Previewable @State var selectedIdx: Int?
    ImageEditChainPanel(
        chain: ImageEditChain(
            documentId: "doc1",
            operations: [
                ImageEditOperation(raw: AnyCodable(["op": "rotate", "page": 1, "params": ["angle": 90]] as [String: Any])),
                ImageEditOperation(raw: AnyCodable(["op": "enhance", "page": 1, "params": ["brightness": 1.2]] as [String: Any])),
                ImageEditOperation(raw: AnyCodable(["op": "remove_background", "page": 1, "params": [:]] as [String: Any]))
            ],
            updatedAt: nil
        ),
        isBusy: false,
        selectedStepIndex: $selectedIdx,
        onRemove: { _ in },
        onReset: {},
        onRotate: { _ in },
        onStraighten: {},
        onEnhance: { _, _, _, _ in },
        onCrop: { _, _, _, _ in },
        onRemoveBackground: {},
        onFuzzyClean: {},
        onSegment: {}
    )
    .frame(width: 260, height: 600)
}

#Preview("Empty") {
    @Previewable @State var selectedIdx: Int?
    ImageEditChainPanel(
        chain: ImageEditChain(documentId: "doc1", operations: [], updatedAt: nil),
        isBusy: false,
        selectedStepIndex: $selectedIdx,
        onRemove: { _ in },
        onReset: {},
        onRotate: { _ in },
        onStraighten: {},
        onEnhance: { _, _, _, _ in },
        onCrop: { _, _, _, _ in },
        onRemoveBackground: {},
        onFuzzyClean: {},
        onSegment: {}
    )
    .frame(width: 260, height: 400)
}
