import SwiftUI

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

    @State var addStepExpanded = false
    @State var enhanceBrightness: Double = 1.0
    @State var enhanceContrast: Double = 1.0
    @State var enhanceSharpen: Double = 1.0
    @State var enhanceAutoLevels = false
    @State var rotateAngle: Double = 0

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
                .accessibilityLabel("Reset all edits")
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
                    // Names its row -- one per edit in the chain, and "this"
                    // means nothing to a reader that cannot see which row has
                    // focus.
                    .accessibilityLabel("Remove step \(index + 1), \(operation.title)")
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

#Preview("With edits") {
    @Previewable @State var selectedIdx: Int?
    ImageEditChainPanel(
        chain: ImageEditChain(
            documentId: "doc1",
            operations: [
                ImageEditOperation(
                    raw: AnyCodable(
                        ["op": "rotate", "page": 1, "params": ["angle": 90]] as [String: Any]
                    )
                ),
                ImageEditOperation(
                    raw: AnyCodable(
                        ["op": "enhance", "page": 1, "params": ["brightness": 1.2]] as [String: Any]
                    )
                ),
                ImageEditOperation(
                    raw: AnyCodable(
                        ["op": "remove_background", "page": 1, "params": [:]] as [String: Any]
                    )
                )
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
