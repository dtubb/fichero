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
        Self.toolIcons[tool.lowercased()] ?? "gearshape"
    }

    private func colorForTool(_ tool: String) -> Color {
        Self.toolColors[tool.lowercased()] ?? .gray
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
