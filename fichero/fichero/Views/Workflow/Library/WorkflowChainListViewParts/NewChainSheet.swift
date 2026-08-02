import SwiftUI

struct NewChainSheet: View {
    let workflows: [WorkflowSidebarItem]
    let onCreate: @MainActor @Sendable (String, String, [ChainStep]) async -> Void
    @Environment(\.dismiss) private var dismiss

    @State private var name = ""
    @State private var description = ""
    @State private var steps: [ChainStep] = []
    @State private var isCreating = false

    init(
        workflows: [WorkflowSidebarItem],
        onCreate: @escaping @MainActor @Sendable (String, String, [ChainStep]) async -> Void
    ) {
        self.workflows = workflows
        self.onCreate = onCreate
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Chain Details") {
                    TextField("Name", text: $name)
                    TextField("Description", text: $description, axis: .vertical)
                        .lineLimit(2...4)
                }

                Section("Steps") {
                    if steps.isEmpty {
                        Text("Add workflows to chain them together")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(Array(steps.enumerated()), id: \.element.id) { index, step in
                            HStack {
                                Text("\(index + 1).")
                                    .foregroundStyle(.secondary)
                                Text(workflowName(for: step.workflowId))
                                Spacer()
                                Button {
                                    steps.remove(at: index)
                                } label: {
                                    Image(systemName: "minus.circle.fill")
                                        .foregroundStyle(.red)
                                }
                                .buttonStyle(.borderless)
                                // Names its row: the chain is an ORDERED list
                                // of steps that can repeat the same workflow,
                                // so the position is part of the identity.
                                .accessibilityLabel(
                                    "Remove step \(index + 1), \(workflowName(for: step.workflowId))"
                                )
                            }
                        }
                        .onMove { from, destination in
                            steps.move(fromOffsets: from, toOffset: destination)
                        }
                    }

                    Menu {
                        ForEach(workflows) { workflow in
                            Button(workflow.name) {
                                addStep(workflowId: workflow.id)
                            }
                        }
                    } label: {
                        Label("Add Workflow", systemImage: "plus")
                    }
                }
            }
            .navigationTitle("New Chain")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }

                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        isCreating = true
                        Task { @MainActor in
                            await createChain()
                        }
                    }
                    .disabled(name.isEmpty || steps.isEmpty || isCreating)
                }
            }
        }
        .frame(minWidth: 400, minHeight: 400)
    }

    private func workflowName(for id: String) -> String {
        workflows.first { $0.id == id }?.name ?? "Unknown"
    }

    private func addStep(workflowId: String) {
        let step = ChainStep(
            id: UUID().uuidString,
            workflowId: workflowId,
            name: "",
            inputMappings: [],
            staticInputs: [:],
            condition: nil,
            continueOnError: false,
            timeoutSeconds: 300
        )
        steps.append(step)
    }

    @MainActor
    private func createChain() async {
        await onCreate(name, description, steps)
        dismiss()
    }
}
