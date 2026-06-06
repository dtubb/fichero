import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "NotesBrowserView")

/// Standalone notes browser (#1500). Lists every Note record, filterable by
/// kind / tag / full-text, and lets the user create free-floating notes
/// (zettels, hubs, fleeting notes) without a document open. Reuses the
/// `DocumentNotesTab` card/edit affordances via `NoteService`.
///
/// Presented as a sheet from the Data menu (`appState.showNotesBrowser`), so it
/// needs no SidebarMode wiring.
struct NotesBrowserView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var apiClient: APIClient
    @StateObject private var service = NoteService()

    @State private var kindFilter: String = ""        // "" = all kinds
    @State private var tagFilter: String = ""
    @State private var searchText: String = ""

    @State private var newText = ""
    @State private var newKind = "zettel"
    @State private var isSaving = false

    @State private var editingId: String?
    @State private var editingText = ""

    /// NoteKind raw values, mirrored from the backend enum (#917).
    private let kinds = ["zettel", "reference", "hub", "inbox", "fleeting", "permanent"]

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            filterBar
            Divider()
            addBar
            Divider()
            notesList
        }
        .frame(minWidth: 520, minHeight: 560)
        .task { await reload() }
    }

    // MARK: - Header

    private var header: some View {
        HStack {
            Text("Notes")
                .font(.headline)
            if !service.isLoading {
                Text("\(service.notes.count)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 1)
                    .background(Capsule().fill(Color(.quaternaryLabelColor).opacity(0.3)))
            }
            Spacer()
            Button("Done") { dismiss() }
                .keyboardShortcut(.cancelAction)
        }
        .padding(12)
    }

    // MARK: - Filter bar

    private var filterBar: some View {
        HStack(spacing: 8) {
            Picker("Kind", selection: $kindFilter) {
                Text("All Kinds").tag("")
                ForEach(kinds, id: \.self) { kind in
                    Text(kind.capitalized).tag(kind)
                }
            }
            .labelsHidden()
            .frame(maxWidth: 160)

            TextField("Tag", text: $tagFilter)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 120)
                .onSubmit { Task { await reload() } }

            TextField("Search…", text: $searchText)
                .textFieldStyle(.roundedBorder)
                .onSubmit { Task { await reload() } }
        }
        .padding(10)
        .onChange(of: kindFilter) { _, _ in Task { await reload() } }
    }

    // MARK: - Add bar

    private var addBar: some View {
        HStack(spacing: 8) {
            Picker("New kind", selection: $newKind) {
                ForEach(kinds, id: \.self) { kind in
                    Text(kind.capitalized).tag(kind)
                }
            }
            .labelsHidden()
            .frame(maxWidth: 130)

            TextField("New note…", text: $newText, axis: .vertical)
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
        .padding(10)
    }

    // MARK: - List

    @ViewBuilder
    private var notesList: some View {
        if service.isLoading {
            ProgressView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = service.error {
            errorState(error)
        } else if service.notes.isEmpty {
            emptyState
        } else {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(service.notes) { note in
                        noteCard(note)
                    }
                }
                .padding(12)
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "pencil.and.scribble")
                .font(.largeTitle)
                .foregroundStyle(.tertiary)
            Text("No notes")
                .foregroundStyle(.secondary)
            Text("Add a note above, or adjust the filters.")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func errorState(_ message: String) -> some View {
        VStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle")
                .font(.largeTitle)
                .foregroundStyle(.orange)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button("Retry") { Task { await reload() } }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    // MARK: - Card

    @ViewBuilder
    private func noteCard(_ note: NoteItem) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if editingId == note.id {
                editingCard(note)
            } else {
                readCard(note)
            }
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color(.quaternaryLabelColor).opacity(0.12))
        )
    }

    private func readCard(_ note: NoteItem) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if let title = note.title, !title.isEmpty {
                Text(title)
                    .font(.callout.weight(.semibold))
            }
            Text(note.body)
                .font(.callout)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)

            HStack(spacing: 6) {
                Text(note.kind.capitalized)
                    .font(.caption2)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 1)
                    .background(Capsule().fill(Color.accentColor.opacity(0.15)))
                ForEach(note.tags, id: \.self) { tag in
                    Text("#\(tag)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("Edit") {
                    editingId = note.id
                    editingText = note.body
                }
                .buttonStyle(.borderless)
                .font(.caption)
                Button(role: .destructive) {
                    Task { try? await service.delete(noteId: note.id) }
                } label: {
                    Image(systemName: "trash").font(.caption)
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

    private func reload() async {
        service.libraryPath = apiClient.currentLibraryPath
        await service.loadAll(kind: kindFilter, tag: tagFilter, query: searchText)
    }

    private func submitNew() {
        let trimmed = newText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        isSaving = true
        Task {
            do {
                _ = try await service.createFree(body: trimmed, kind: newKind)
                newText = ""
            } catch {
                logger.error("create free note failed: \(error.localizedDescription)")
            }
            isSaving = false
        }
    }

    private func saveEdit(_ note: NoteItem) async {
        let trimmed = editingText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        do {
            _ = try await service.update(noteId: note.id, body: trimmed)
            editingId = nil
        } catch {
            logger.error("update note failed: \(error.localizedDescription)")
        }
    }
}
