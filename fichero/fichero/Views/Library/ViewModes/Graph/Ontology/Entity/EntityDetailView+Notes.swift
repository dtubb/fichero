import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "EntityNotesSection")

/// Notes sub-section for the entity inspector (#1501). Lists notes linked to
/// the current KG entity (`GET /api/notes?linked_entity_id={id}`) and lets the
/// user add a free-text bio/summary note, created with `kind=reference`.
///
/// Self-contained: owns its own `NoteService`, keyed on `entityId` via
/// `.task(id:)` so it reloads when the inspector navigates to another entity.
/// Mirrors the `DocumentNotesTab` card/edit affordances.
struct EntityNotesSection: View {
    let entityId: String

    @Environment(NoteStore.self) private var noteStore
    @State private var newText = ""
    @State private var editingId: String?
    @State private var editingText = ""
    @State private var isSaving = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Notes")
                .font(.subheadline)
                .fontWeight(.semibold)

            addBar
            notesList
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .task(id: entityId) {
            guard !entityId.isEmpty else { return }
            await noteStore.loadNotes(forEntity: entityId)
        }
    }

    // MARK: - Add bar

    private var addBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "pencil")
                .foregroundStyle(.secondary)
            TextField("Add a note about this entity…", text: $newText, axis: .vertical)
                .textFieldStyle(.plain)
                .lineLimit(1...4)
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
    }

    // MARK: - List

    @ViewBuilder
    private var notesList: some View {
        if noteStore.isLoading {
            ProgressView()
                .frame(maxWidth: .infinity)
                .padding(.vertical, 8)
        } else if noteStore.notes.isEmpty {
            Text("No notes linked to this entity yet.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(noteStore.notes) { note in
                    noteCard(note)
                }
            }
        }
    }

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
                .fill(Color(platformColor: .platformQuaternaryLabel).opacity(0.12))
        )
    }

    private func readCard(_ note: NoteItem) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(note.body ?? "")
                .font(.callout)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
            HStack {
                Text((note.kind?.rawValue ?? "reference").capitalized)
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
                    Task { try? await noteStore.delete(noteId: noteId) }
                } label: {
                    Image(systemName: "trash").font(.caption)
                }
                .buttonStyle(.borderless)
                .foregroundStyle(.red)
                .help("Delete this note")
            }
        }
    }

    private func editingCard(_ note: NoteItem) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            TextEditor(text: $editingText)
                .editorScaledFont(.callout)
                .frame(minHeight: 60)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color.accentColor.opacity(0.5), lineWidth: 1)
                )
            HStack {
                Button("Cancel") { editingId = nil }
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
        guard !trimmed.isEmpty, !entityId.isEmpty else { return }
        isSaving = true
        Task {
            do {
                _ = try await noteStore.createForEntity(entityId, body: trimmed)
                newText = ""
            } catch {
                logger.error("create entity note failed: \(error.localizedDescription)")
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
            logger.error("update entity note failed: \(error.localizedDescription)")
        }
    }
}
