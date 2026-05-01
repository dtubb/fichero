import SwiftUI

/// Row displaying a workflow in the library list
struct WorkflowLibraryRow: View {
    let workflow: WorkflowSidebarItem

    var body: some View {
        HStack {
            Image(systemName: "flowchart")
                .font(.title2)
                .foregroundColor(.accentColor)
                .frame(width: 32)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    Text(workflow.name)
                        .font(.headline)
                    if workflow.isSystem {
                        Image(systemName: "lock.fill")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }

                if let desc = workflow.description, !desc.isEmpty {
                    Text(desc)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }

                HStack(spacing: 8) {
                    Label("\(workflow.nodeCount) nodes", systemImage: "square.on.circle")
                    Label("\(workflow.edgeCount) connections", systemImage: "arrow.right")
                }
                .font(.caption2)
                .foregroundColor(.secondary)
            }

            Spacer()
        }
        .padding(.vertical, 4)
    }
}
