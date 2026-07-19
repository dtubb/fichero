import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "DocumentNotesTab")

/// Notes tab in the Document Inspector (#1355), rebuilt as List + detail.
struct DocumentNotesTab: View {
    let document: Document

    @Environment(NoteStore.self) private var noteStore
    @State private var focused = FocusedNote.shared
    @State private var newText = ""
    @State private var isSaving = false
    @FocusState private var newFieldFocused: Bool

    private var noteItems: [NoteSelectionItem] {
        noteStore.notes.map(NoteSelectionItem.init)
    }

    var body: some View {
        VStack(spacing: 0) {
            addBar
            Divider()
            NotesInspectorPane(
                notes: noteItems,
                selectionResetToken: document.id,
                documentName: document.name,
                focused: focused
            )
        }
        .task(id: document.id) {
            focused.clear()
            focused.documentName = document.name
            await loadNotes()
        }
    }

    // MARK: - Add bar

    private var addBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "pencil")
                .foregroundStyle(.secondary)

            TextField("Add a note…", text: $newText, axis: .vertical)
                .textFieldStyle(.plain)
                .lineLimit(1...4)
                .focused($newFieldFocused)
                .onSubmit { submitNew() }

            Button {
                submitNew()
            } label: {
                if isSaving {
                    ProgressView().controlSize(.small)
                } else {
                    Text("Add")
                }
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .disabled(newText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSaving)
        }
        .padding(10)
    }

    // MARK: - Actions

    private func submitNew() {
        let trimmed = newText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        isSaving = true
        Task {
            do {
                _ = try await createNote(body: trimmed)
                newText = ""
                newFieldFocused = false
            } catch {
                logger.error("create note failed: \(error.localizedDescription)")
            }
            isSaving = false
        }
    }

    private func loadNotes() async {
        switch document.docType {
        case .folder:
            await noteStore.loadNotes(forFolder: document.id)
        case .page:
            await noteStore.loadNotes(forPage: document.id)
        default:
            await noteStore.loadNotes(forDocument: document.id)
        }
    }

    private func createNote(body: String) async throws -> NoteItem {
        switch document.docType {
        case .folder:
            return try await noteStore.createForFolder(document.id, body: body)
        case .page:
            return try await noteStore.createForPage(document.id, body: body)
        default:
            return try await noteStore.createForDocument(document.id, body: body)
        }
    }
}
