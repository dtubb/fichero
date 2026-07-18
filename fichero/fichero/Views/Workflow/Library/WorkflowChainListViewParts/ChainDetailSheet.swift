import SwiftUI

struct ChainDetailSheet: View {
    let chain: WorkflowChain
    let workflows: [WorkflowSidebarItem]
    let onExecute: () -> Void
    let onDelete: () -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ChainDetailContent(
                chain: chain,
                workflows: workflows,
                onExecute: onExecute,
                onDelete: {
                    dismiss()
                    onDelete()
                }
            )
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .frame(minWidth: 500, minHeight: 400)
    }
}
