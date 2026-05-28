import SwiftUI

/// "+ Add" picker (A5): choose library documents to place into a room. Each
/// selected document becomes a node (`place_node` with its `source_id`) — the
/// backend owns placement (`feedback_kg_logic_in_backend`). Placing a node
/// never mutates the Library; a room is a view, not a container.
///
/// Collection / smart-group expansion is a follow-up; v1 lists documents.
struct AddToRoomPicker: View {
    let roomId: String
    var onComplete: () -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    @State private var selection = Set<String>()
    @State private var isAdding = false
    @State private var addError: String?

    private var documents: [Document] {
        let manager = LibraryManager.shared
        let library = manager.currentLibraryId.flatMap { manager.getLibrary(id: $0) }
            ?? manager.openLibraries.first
            ?? manager.globalLibrary
        let all = library?.documentStore.currentDocuments ?? []
        let nonFolders = all.filter { $0.docType != .folder }
        guard !query.isEmpty else { return nonFolders }
        return nonFolders.filter { $0.name.localizedCaseInsensitiveContains(query) }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Add Sources to Room").font(.headline)
                Spacer()
            }
            .padding(12)
            Divider()

            TextField("Search documents", text: $query)
                .textFieldStyle(.roundedBorder)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)

            List(documents, id: \.id, selection: $selection) { doc in
                Label(doc.name, systemImage: "doc.text")
                    .tag(doc.id)
            }
            .frame(minHeight: 240)

            if let addError {
                Text(addError).font(.caption).foregroundStyle(.red).padding(.horizontal, 12)
            }

            Divider()
            HStack {
                Text("\(selection.count) selected").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button("Cancel") { dismiss() }
                Button("Add") { Task { await add() } }
                    .buttonStyle(.borderedProminent)
                    .disabled(selection.isEmpty || isAdding)
            }
            .padding(12)
        }
        .frame(width: 460, height: 420)
    }

    private func add() async {
        guard let service = activeMindPalaceService() else { return }
        isAdding = true
        addError = nil
        defer { isAdding = false }
        do {
            for docId in selection {
                let label = documents.first { $0.id == docId }?.name
                try await service.placeNode(
                    roomId: roomId,
                    nodeType: .source,
                    sourceId: docId,
                    label: label
                )
            }
            onComplete()
            dismiss()
        } catch {
            addError = error.localizedDescription
        }
    }
}
