import SwiftUI

/// Card representation of a workflow node for Icon view
struct WorkflowNodeCard: View {
    let node: WorkflowNode
    var executionState: NodeExecutionState?

    var body: some View {
        VStack(spacing: 8) {
            // Icon with execution state overlay
            ZStack {
                Image(systemName: iconForTool(node.tool))
                    .font(.system(size: 32))
                    .foregroundStyle(colorForTool(node.tool))
                    .frame(width: 50, height: 50)
                    .background(colorForTool(node.tool).opacity(0.15))
                    .clipShape(RoundedRectangle(cornerRadius: 10))

                // Execution state overlay
                if let state = executionState {
                    executionOverlay(for: state)
                }
            }

            // Label
            Text(node.label ?? node.tool)
                .font(.caption)
                .fontWeight(.medium)
                .lineLimit(2)
                .multilineTextAlignment(.center)

            // Tool type
            Text(node.tool)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(width: 140, height: 120)
        .padding(8)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color(.separatorColor), lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.15), radius: 3, x: 0, y: 2)
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

    @ViewBuilder
    private func executionOverlay(for state: NodeExecutionState) -> some View {
        VStack {
            Spacer()
            HStack {
                Spacer()
                switch state.status {
                case .running, .parallelRunning:
                    ProgressView()
                        .controlSize(.small)
                        .scaleEffect(0.7)
                        .padding(4)
                        .background(.ultraThickMaterial)
                        .clipShape(Circle())
                case .completed:
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                        .padding(4)
                        .background(.ultraThickMaterial)
                        .clipShape(Circle())
                case .failed:
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.red)
                        .padding(4)
                        .background(.ultraThickMaterial)
                        .clipShape(Circle())
                case .idle:
                    EmptyView()
                }
            }
        }
    }
}
