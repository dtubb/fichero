import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "SimpleWorkflowView")

/// Simple workflow editor for testing
struct SimpleWorkflowView: View {
    @Binding var editingWorkflow: SimpleWorkflow
    @State private var isSaving: Bool = false

    var body: some View {
        VStack {
            Text("Workflow: \(editingWorkflow.name)")
                .font(.title)

            Button {
                logger.info("Saving workflow: \(editingWorkflow.name)")
                isSaving = true
                Task {
                    try? await Task.sleep(for: .seconds(1))
                    guard !Task.isCancelled else { return }
                    isSaving = false
                }
            } label: {
                HStack {
                    if isSaving {
                        ProgressView()
                            .scaleEffect(0.7)
                    } else {
                        Text("Save")
                    }
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(isSaving)
        }
        .padding()
    }
}

/// Simple workflow model for testing
struct SimpleWorkflow: Identifiable, Codable {
    let id: String
    var name: String
    var description: String

    init(name: String, description: String = "") {
        self.id = UUID().uuidString
        self.name = name
        self.description = description
    }
}

#Preview {
    SimpleWorkflowView(
        editingWorkflow: .constant(SimpleWorkflow(name: "Test Workflow"))
    )
}
