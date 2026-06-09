import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "DocumentNotesTab")

/// Notes tab in the Document Inspector. Wires `NoteService` → `/api/notes`.
/// Lists free-text notes linked to this document; lets the user add, inline-edit,
/// and delete notes. (#1355)
struct DocumentNotesTab: View {
    let document: Document

    @Environment(NoteStore.self) private var noteStore
    @State private var newText = ""
    @State private var editingId: String?
    @State private var editingText = ""
    @State private var isSaving = false
    @State private var selectedNoteId: NoteItem.ID?
    @FocusState private var newFieldFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            addBar
            Divider()
            notesList
        }
        .task(id: document.id) {
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

    // MARK: - Notes list

    @ViewBuilder
    private var notesList: some View {
        if noteStore.isLoading {
            ProgressView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if noteStore.notes.isEmpty {
            emptyState
        } else {
            List(selection: $selectedNoteId) {
                ForEach(noteStore.notes) { note in
                    noteRow(note)
                        .listRowInsets(EdgeInsets(top: 6, leading: 10, bottom: 6, trailing: 10))
                        .contextMenu {
                            noteContextMenu(note)
                        }
                }
            }
            .listStyle(.inset)
        }
    }

    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "pencil.and.scribble")
                .font(.largeTitle)
                .foregroundStyle(.tertiary)
            Text("No notes yet")
                .foregroundStyle(.secondary)
            Text("Type above to add the first note.")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Note row

    @ViewBuilder
    private func noteRow(_ note: NoteItem) -> some View {
        if editingId == note.id ?? "" {
            editingCard(note)
        } else {
            readCard(note)
        }
    }

    // MARK: - Context menu

    @ViewBuilder
    private func noteContextMenu(_ note: NoteItem) -> some View {
        Button("Edit") {
            editingId = note.id ?? ""
            editingText = note.body ?? ""
        }
        Divider()
        Button("Delete", role: .destructive) {
            guard let noteId = note.id else { return }
            Task { await deleteNote(noteId: noteId) }
        }
    }

    private func readCard(_ note: NoteItem) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(note.body ?? "")
                .font(.callout)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)

            HStack {
                Text(relativeDate(note.updatedAt))
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                Spacer()
                Button("Edit") {
                    editingId = note.id ?? ""
                    editingText = note.body ?? ""
                }
                .buttonStyle(.borderless)
                .font(.caption)
                Button(role: .destructive) {
                    guard let noteId = note.id else { return }
                    Task { await deleteNote(noteId: noteId) }
                } label: {
                    Image(systemName: "trash")
                        .font(.caption)
                }
                .buttonStyle(.borderless)
                .foregroundStyle(.red)
            }
        }
    }

    private func editingCard(_ note: NoteItem) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            TextEditor(text: $editingText)
                .font(.callout)
                .frame(minHeight: 60)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color.accentColor.opacity(0.5), lineWidth: 1)
                )

            HStack {
                Button("Cancel") {
                    editingId = nil
                }
                .buttonStyle(.borderless)
                .font(.caption)
                Spacer()
                Button("Save") {
                    Task { await saveEdit(note) }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(editingText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
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

    private func saveEdit(_ note: NoteItem) async {
        let trimmed = editingText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, let noteId = note.id else { return }
        do {
            _ = try await noteStore.update(noteId: noteId, body: trimmed)
            editingId = nil
        } catch {
            logger.error("update note failed: \(error.localizedDescription)")
        }
    }

    private func relativeDate(_ date: Date?) -> String {
        guard let date else { return "" }
        let rel = RelativeDateTimeFormatter()
        rel.unitsStyle = .abbreviated
        return rel.localizedString(for: date, relativeTo: Date())
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

    private func deleteNote(noteId: String) async {
        do {
            try await noteStore.delete(noteId: noteId)
        } catch {
            logger.error("delete note failed: \(error.localizedDescription)")
        }
    }
}
