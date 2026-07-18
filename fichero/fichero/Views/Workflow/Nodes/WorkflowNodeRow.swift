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
        switch tool.lowercased() {
        case "files", "collection", "search": return "doc.on.doc"
        case "describe", "analyze": return "eye"
        case "transcribe": return "waveform"
        case "summarize", "translate", "classify": return "text.bubble"
        case "enhance", "crop", "rotate", "segment": return "wand.and.stars"
        case "to_pdf", "to_word", "to_excel", "to_json": return "arrow.triangle.2.circlepath"
        case "if", "switch": return "questionmark.diamond"
        case "loop", "merge": return "arrow.triangle.branch"
        case "agent": return "brain"
        default: return "gearshape"
        }
    }

    private func colorForTool(_ tool: String) -> Color {
        switch tool.lowercased() {
        case "files", "collection", "search": return .green
        case "describe", "analyze", "transcribe": return .blue
        case "summarize", "translate", "classify": return .purple
        case "enhance", "crop", "rotate", "segment": return .orange
        case "to_pdf", "to_word", "to_excel", "to_json": return .cyan
        case "if", "switch", "loop", "merge": return .yellow
        case "agent": return .pink
        default: return .gray
        }
    }
}
