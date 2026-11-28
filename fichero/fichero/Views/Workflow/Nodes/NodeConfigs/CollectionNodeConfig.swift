import SwiftUI

/// Configuration view for collection node
struct CollectionNodeConfig: View {
    @Binding var node: WorkflowNode

    @Environment(DocumentStore.self) var documentStore: DocumentStore

    @State private var collectionId: String = ""

    private var folderOptions: [WorkflowFolderOption] {
        WorkflowFolderOption.tree(from: documentStore.collections)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Collection")
                .font(.caption)
                .foregroundColor(.secondary)

            Picker("Select collection", selection: $collectionId) {
                Text("Select...").tag("")
                ForEach(folderOptions) { option in
                    Text(option.indentedName).tag(option.folder.id)
                }
            }
            .pickerStyle(.menu)
            .onChange(of: collectionId) { _, newValue in
                if node.config == nil {
                    node.config = [:]
                }
                node.config?["collection_id"] = .string(newValue)
            }
            if folderOptions.isEmpty {
                Text("No folders found. Create a folder in the project first.")
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .italic()
            }
        }
        .task {
            if documentStore.collections.isEmpty {
                await documentStore.loadCollections()
            }
        }
        .onAppear {
            loadInitialState()
        }
        .onChange(of: documentStore.collections) { _, _ in
            guard !collectionId.isEmpty else { return }
            if !folderOptions.contains(where: { $0.id == collectionId }) {
                collectionId = ""
                if node.config == nil {
                    node.config = [:]
                }
                node.config?["collection_id"] = .string("")
            }
        }
    }

    private func loadInitialState() {
        if let configValue = node.config?["collection_id"],
           case .string(let id) = configValue {
            collectionId = id
        }
    }
}
