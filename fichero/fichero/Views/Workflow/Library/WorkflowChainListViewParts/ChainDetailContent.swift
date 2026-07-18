import SwiftUI

struct ChainDetailContent: View {
    let chain: WorkflowChain
    let workflows: [WorkflowSidebarItem]
    let onExecute: () -> Void
    let onDelete: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text(chain.name)
                        .font(.largeTitle)
                        .fontWeight(.bold)

                    if !chain.description.isEmpty {
                        Text(chain.description)
                            .font(.body)
                            .foregroundStyle(.secondary)
                    }
                }

                Divider()

                // Steps
                VStack(alignment: .leading, spacing: 12) {
                    Text("Steps")
                        .font(.headline)

                    if chain.steps.isEmpty {
                        Text("No steps defined")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(Array(chain.steps.enumerated()), id: \.element.id) { index, step in
                            ChainStepRow(
                                step: step,
                                index: index,
                                workflowName: workflowName(for: step.workflowId)
                            )
                        }
                    }
                }

                Divider()

                // Actions
                HStack(spacing: 16) {
                    Button {
                        onExecute()
                    } label: {
                        Label("Execute Chain", systemImage: "play.fill")
                    }
                    .buttonStyle(.borderedProminent)

                    Button(role: .destructive) {
                        onDelete()
                    } label: {
                        Label("Delete", systemImage: "trash")
                    }
                }
            }
            .padding()
        }
        .navigationTitle(chain.name)
    }

    private func workflowName(for id: String) -> String {
        workflows.first { $0.id == id }?.name ?? "Unknown Workflow"
    }
}
