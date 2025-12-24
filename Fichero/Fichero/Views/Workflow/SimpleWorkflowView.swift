import SwiftUI

/// Simple workflow editor for testing
struct SimpleWorkflowView: View {
    @Binding var editingWorkflow: SimpleWorkflow
    @State private var isSaving: Bool = false
    
    var body: some View {
        VStack {
            Text("Workflow: \(editingWorkflow.name)")
                .font(.title)
            
            Button(action: {
                print("Saving workflow: \(editingWorkflow.name)")
                isSaving = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
                    isSaving = false
                }
            }) {
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