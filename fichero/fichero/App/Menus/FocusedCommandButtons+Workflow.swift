import SwiftUI

/// Button that runs a workflow on selected documents
struct FocusedRunWorkflowOnSelectionButton: View {
    @FocusedValue(\.runWorkflowOnSelection) private var runWorkflowOnSelection
    @ObservedObject var featureManager = FeatureManager.shared

    var body: some View {
        if featureManager.isWorkflowRunOnSelectionEnabled {
            Button("Run Workflow on Selection...") {
                runWorkflowOnSelection?()
            }
            .keyboardShortcut("r", modifiers: [.command, .shift])
            .disabled(runWorkflowOnSelection == nil)
        }
    }
}
