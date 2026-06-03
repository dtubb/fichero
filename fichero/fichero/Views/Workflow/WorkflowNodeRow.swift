import SwiftUI

/// Row representation of a workflow node for List view
struct WorkflowNodeRow: View {
    let node: WorkflowNode
    var executionState: NodeExecutionState?

    var body: some View {
        HStack(spacing: 12) {
            // Icon with execution indicator
            ZStack {
                Image(systemName: iconForTool(node.tool))
                    .font(.title2)
                    .foregroundStyle(colorForTool(node.tool))
                    .frame(width: 36, height: 36)
                    .background(colorForTool(node.tool).opacity(0.15))
                    .clipShape(RoundedRectangle(cornerRadius: 8))

                // Execution state indicator
                if let state = executionState, state.status != .idle {
                    VStack {
                        Spacer()
                        HStack {
                            Spacer()
                            executionBadge(for: state)
                        }
                    }
                }
            }
            .frame(width: 36, height: 36)

            // Info
            VStack(alignment: .leading, spacing: 2) {
                Text(node.label ?? node.tool)
                    .font(.body)
                    .fontWeight(.medium)

                HStack(spacing: 8) {
                    Text(node.tool)
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    if !node.inputMappings.isEmpty {
                        Text("•")
                            .foregroundStyle(.tertiary)
                        Text("\(node.inputMappings.count) input(s)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    // Show progress for parallel execution
                    if let state = executionState, state.fileTotal > 0 {
                        Text("•")
                            .foregroundStyle(.tertiary)
                        Text("\(state.successCount + state.errorCount)/\(state.fileTotal)")
                            .font(.caption)
                            .foregroundStyle(.blue)
                    }
                }
            }

            Spacer()

            // Position badge
            Text("(\(Int(node.positionX)), \(Int(node.positionY)))")
                .font(.caption)
                .foregroundStyle(.tertiary)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(.quaternary)
                .clipShape(Capsule())
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private func executionBadge(for state: NodeExecutionState) -> some View {
        switch state.status {
        case .running, .parallelRunning:
            ProgressView()
                .controlSize(.mini)
                .scaleEffect(0.7)
        case .completed:
            Image(systemName: "checkmark.circle.fill")
                .font(.caption2)
                .foregroundColor(.green)
        case .failed:
            Image(systemName: "xmark.circle.fill")
                .font(.caption2)
                .foregroundColor(.red)
        case .idle:
            EmptyView()
        }
    }

    private func iconForTool(_ tool: String) -> String {
        Self.toolIcons[tool.lowercased()] ?? "gearshape"
    }

    private func colorForTool(_ tool: String) -> Color {
        Self.toolColors[tool.lowercased()] ?? .gray
    }

    private static let toolIcons: [String: String] = [
        "files": "doc.on.doc", "collection": "doc.on.doc", "search": "doc.on.doc",
        "describe": "eye", "analyze": "eye", "transcribe": "waveform",
        "summarize": "text.bubble", "translate": "text.bubble", "classify": "text.bubble",
        "enhance": "wand.and.stars", "crop": "wand.and.stars",
        "rotate": "wand.and.stars", "segment": "wand.and.stars",
        "to_pdf": "arrow.triangle.2.circlepath",
        "to_word": "arrow.triangle.2.circlepath",
        "to_excel": "arrow.triangle.2.circlepath",
        "to_json": "arrow.triangle.2.circlepath",
        "if": "questionmark.diamond", "switch": "questionmark.diamond",
        "loop": "arrow.triangle.branch",
        "aggregate": "arrow.triangle.merge", "merge": "arrow.triangle.merge",
        "agent": "brain"
    ]

    private static let toolColors: [String: Color] = [
        "files": .green, "collection": .green, "search": .green,
        "describe": .blue, "analyze": .blue, "transcribe": .blue,
        "summarize": .purple, "translate": .purple, "classify": .purple,
        "enhance": .orange, "crop": .orange, "rotate": .orange, "segment": .orange,
        "to_pdf": .cyan, "to_word": .cyan, "to_excel": .cyan, "to_json": .cyan,
        "if": .yellow, "switch": .yellow, "loop": .yellow,
        "aggregate": .teal, "merge": .teal,
        "agent": .pink
    ]
}
