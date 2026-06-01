import SwiftUI

// swiftlint:disable type_body_length file_length

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
    let onEnhance: (Double, Double, Double, Bool) -> Void
    let onRemoveBackground: () -> Void
    let onFuzzyClean: () -> Void
    let onSegment: () -> Void

    @State private var addStepExpanded = false
    @State private var enhanceBrightness: Double = 1.0
    @State private var enhanceContrast: Double = 1.0
    @State private var enhanceSharpen: Double = 1.0
    @State private var enhanceAutoLevels = false

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
        .frame(height: 44)
    }

    // MARK: - Chain

    @ViewBuilder
    private var chainSection: some View {
        if chain.isEmpty {
            emptyChainState
        } else {
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(Array(chain.operations.enumerated()), id: \.element.id) { index, op in
                        stepRow(index: index, op: op)
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
    private func stepRow(index: Int, op: ImageEditOperation) -> some View {
        let isSelected = selectedStepIndex == index
        VStack(alignment: .leading, spacing: 0) {
            Button {
                withAnimation(.easeInOut(duration: 0.12)) {
                    if isSelected {
                        selectedStepIndex = nil
                    } else {
                        selectedStepIndex = index
                        seedEnhanceSliders(from: op)
                    }
                }
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: op.icon)
                        .frame(width: 22)
                        .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(op.title).font(.subheadline)
                        if !op.summary.isEmpty {
                            Text(op.summary).font(.caption).foregroundStyle(.secondary)
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
                stepEditor(for: op, at: index)
                    .padding(.horizontal, 12)
                    .padding(.bottom, 10)
            }
        }
    }

    @ViewBuilder
    private func stepEditor(for op: ImageEditOperation, at index: Int) -> some View {
        switch op.opKind {
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
            let angle = (op.params["angle"] as? Double) ?? Double(op.params["angle"] as? Int ?? 0)
            HStack {
                Image(systemName: "info.circle").foregroundStyle(.secondary)
                Text("Rotated \(Int(angle))°. Remove and re-add to change.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        case "crop":
            let width = op.params["width"] as? Int ?? 0
            let height = op.params["height"] as? Int ?? 0
            HStack {
                Image(systemName: "info.circle").foregroundStyle(.secondary)
                Text("Cropped to \(width)×\(height) px.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        default:
            HStack {
                Image(systemName: "info.circle").foregroundStyle(.secondary)
                Text("Remove and re-add to change settings.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func seedEnhanceSliders(from op: ImageEditOperation) {
        guard op.opKind == "enhance" else { return }
        enhanceBrightness = (op.params["brightness"] as? Double) ?? 1.0
        enhanceContrast = (op.params["contrast"] as? Double) ?? 1.0
        enhanceSharpen = (op.params["sharpen"] as? Double) ?? 1.0
        enhanceAutoLevels = (op.params["auto_levels"] as? Bool) ?? false
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
                addToolButton("sparkles", title: "Fuzzy Clean") {
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

// swiftlint:enable type_body_length file_length

#Preview("With edits") {
    @Previewable @State var selectedIdx: Int? = nil
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
        onEnhance: { _, _, _, _ in },
        onRemoveBackground: {},
        onFuzzyClean: {},
        onSegment: {}
    )
    .frame(width: 260, height: 600)
}

#Preview("Empty") {
    @Previewable @State var selectedIdx: Int? = nil
    ImageEditChainPanel(
        chain: ImageEditChain(documentId: "doc1", operations: [], updatedAt: nil),
        isBusy: false,
        selectedStepIndex: $selectedIdx,
        onRemove: { _ in },
        onReset: {},
        onRotate: { _ in },
        onEnhance: { _, _, _, _ in },
        onRemoveBackground: {},
        onFuzzyClean: {},
        onSegment: {}
    )
    .frame(width: 260, height: 400)
}
