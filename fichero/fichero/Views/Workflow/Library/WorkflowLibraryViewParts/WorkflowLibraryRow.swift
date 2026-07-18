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
                    Text(workflow.displayName)
                        .font(.headline)
                    if workflow.isSystem {
                        Image(systemName: "lock.fill")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }

                if let desc = workflow.description, !desc.isEmpty {
                    // Wrap to as many lines as the description needs — was
                    // truncating at 2 lines + ellipsis, which clipped useful
                    // detail (#931). \`fixedSize(vertical: true)\` lets the row
                    // grow to fit the wrapped text instead of compressing it.
                    Text(desc)
                        .font(.caption)
                        .foregroundColor(.secondary)
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
