import SwiftUI

extension ActivitySidebarContent {

    @ViewBuilder
    func workflowSection(group: ActivityWorkflowGroup, runs: [ActivityRun]) -> some View {
        DisclosureGroup(
            isExpanded: Binding(
                get: { isWorkflowExpanded(group.id) },
                set: { setWorkflowExpanded(group.id, expanded: $0) }
            )
        ) {
            ForEach(runs) { run in
                runDisclosure(run)
            }
        } label: {
            HStack(spacing: 8) {
                Image(systemName: "arrow.triangle.branch")
                    .foregroundStyle(.secondary)
                    .frame(width: 16)

                Text(group.displayName)
                    .font(.subheadline)
                    .fontWeight(.medium)

                Spacer()

                Text("\(runs.count)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.secondary.opacity(0.15), in: Capsule())
            }
        }
    }
}
