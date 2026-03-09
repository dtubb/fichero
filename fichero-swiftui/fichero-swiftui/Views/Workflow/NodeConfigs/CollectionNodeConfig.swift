import SwiftUI

/// Configuration view for collection node
struct CollectionNodeConfig: View {
    @Binding var node: WorkflowNode

    @EnvironmentObject var documentStore: DocumentStore

    @State private var collectionId: String = ""

    private var folders: [Document] {
        documentStore.collections
            .filter { $0.docType == .folder }
            .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Collection")
                .font(.caption)
                .foregroundColor(.secondary)

            Picker("Select collection", selection: $collectionId) {
                Text("Select...").tag("")
                ForEach(folders, id: \.id) { folder in
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
            if folders.isEmpty {
                Text("No folders found. Create a folder in Library first.")
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
    }

    private func loadInitialState() {
        if let configValue = node.config?["collection_id"],
           case .string(let id) = configValue {
            collectionId = id
        }
    }
}
