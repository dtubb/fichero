import SwiftUI

/// Configuration view for collection node
struct CollectionNodeConfig: View {
    @Binding var node: WorkflowNode
    
    @EnvironmentObject var documentStore: DocumentStore
    
    @State private var collectionId: String = ""
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Collection")
                .font(.caption)
                .foregroundColor(.secondary)
            
            Picker("Select collection", selection: $collectionId) {
                Text("Select...").tag("")
                ForEach(documentStore.collections.filter { $0.docType == .folder }, id: \.id) { folder in
                    Text(folder.name).tag(folder.id)
                }
            }
            .pickerStyle(.menu)
            .onChange(of: collectionId) { _, newValue in
                if node.config == nil {
                    node.config = [:]
                }
                node.config?["collection_id"] = .string(newValue)
            }
        }
        .onAppear {
            loadInitialState()
        }
    }
    
    private func loadInitialState() {
        if let configValue = node.config?["collection_id"],
           case .string(let id) = configValue {
            collectionId = id
        }
    }
}
