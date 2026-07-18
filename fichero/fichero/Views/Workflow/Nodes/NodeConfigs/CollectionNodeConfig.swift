import SwiftUI

private struct FolderPickerOption: Identifiable {
    let folder: Document
    let depth: Int

    var id: String { folder.id }

    var indentedName: String {
        String(repeating: "  ", count: depth) + folder.name
    }
}

/// Configuration view for collection node
struct CollectionNodeConfig: View {
    @Binding var node: WorkflowNode

    @Environment(DocumentStore.self) var documentStore: DocumentStore

    @State private var collectionId: String = ""

    private var folderOptions: [FolderPickerOption] {
        buildFolderOptions(from: documentStore.collections)
    }

    private var foldersById: [String: Document] {
        Dictionary(uniqueKeysWithValues: folderOptions.map { ($0.folder.id, $0.folder) })
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
        .onChange(of: documentStore.collections) { _, _ in
            guard !collectionId.isEmpty else { return }
            if foldersById[collectionId] == nil {
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

    private func buildFolderOptions(from documents: [Document]) -> [FolderPickerOption] {
        let allFolders = documents
            .filter { $0.docType == .folder }
            .sorted { lhs, rhs in
                lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
            }

        let validFolderIds = Set(allFolders.map(\.id))

        var childrenMap: [String: [Document]] = [:]
        for folder in allFolders {
            guard let parentId = folder.parentId, validFolderIds.contains(parentId) else { continue }
            childrenMap[parentId, default: []].append(folder)
        }

        for key in childrenMap.keys {
            childrenMap[key]?.sort { lhs, rhs in
                lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
            }
        }

        let inboxRoots = allFolders.filter { $0.parentId == nil && $0.name == "Inbox" }
        let otherRoots = allFolders
            .filter { folder in
                folder.parentId == nil && folder.name != "Inbox"
            }
            .sorted { lhs, rhs in
                lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
            }
        let orderedRoots = inboxRoots + otherRoots

        var options: [FolderPickerOption] = []

        func traverse(_ folder: Document, depth: Int) {
            options.append(FolderPickerOption(folder: folder, depth: depth))
            for child in childrenMap[folder.id] ?? [] {
                traverse(child, depth: depth + 1)
            }
        }

        for root in orderedRoots {
            traverse(root, depth: 0)
        }

        return options
    }
}
