import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "DocumentNotesTab")

/// Notes tab in the Document Inspector. Wires `NoteService` → `/api/notes`.
/// Lists free-text notes linked to this document; lets the user add, inline-edit,
/// and delete notes. (#1355)
struct DocumentNotesTab: View {
    let document: Document

    @EnvironmentObject private var apiClient: APIClient
    @StateObject private var service = NoteService()
    @State private var newText = ""
    @State private var editingId: String?
    @State private var editingText = ""
    @State private var isSaving = false
    @FocusState private var newFieldFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            addBar
            Divider()
            notesList
        }
        .task(id: document.id) {
            service.libraryPath = apiClient.currentLibraryPath
            await service.load(linkedDocumentId: document.id)
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
        if service.isLoading {
            ProgressView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if service.notes.isEmpty {
            emptyState
        } else {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(service.notes) { note in
                        noteCard(note)
                    }
                }
                .padding(10)
            }
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

    // MARK: - Note card

    @ViewBuilder
    private func noteCard(_ note: NoteItem) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if editingId == note.id ?? "" {
                editingCard(note)
            } else {
                readCard(note)
            }
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color(.quaternaryLabelColor).opacity(0.1))
        )
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
                    Task { try? await service.delete(noteId: noteId) }
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
                _ = try await service.create(body: trimmed, linkedDocumentId: document.id)
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
            _ = try await service.update(noteId: noteId, body: trimmed)
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
}
