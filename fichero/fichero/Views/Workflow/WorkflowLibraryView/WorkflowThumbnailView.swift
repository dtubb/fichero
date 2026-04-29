import SwiftUI

/// Thumbnail view for workflow grid/icon mode
/// Shows a mini preview of the workflow structure
struct WorkflowThumbnailView: View {
    let workflow: WorkflowSidebarItem
    let isSelected: Bool

    var body: some View {
        VStack(spacing: 8) {
            // Mini workflow preview (visual representation of nodes/edges)
            WorkflowMiniPreview(nodeCount: workflow.nodeCount, edgeCount: workflow.edgeCount)
                .frame(width: 120, height: 80)
                .background(Color(.controlBackgroundColor))
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(isSelected ? Color.accentColor : Color.clear, lineWidth: 2)
                )

            // Workflow name
            HStack(spacing: 2) {
                Text(workflow.name)
                    .font(.caption)
                    .fontWeight(.medium)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
                if workflow.isSystem {
                    Image(systemName: "lock.fill")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
            .frame(width: 120)

            // Stats
            HStack(spacing: 4) {
                Image(systemName: "square.on.circle")
                Text("\(workflow.nodeCount)")
                Image(systemName: "arrow.right")
                Text("\(workflow.edgeCount)")
            }
            .font(.caption2)
            .foregroundColor(.secondary)
        }
        .padding(8)
        .background(isSelected ? Color.accentColor.opacity(0.1) : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}
