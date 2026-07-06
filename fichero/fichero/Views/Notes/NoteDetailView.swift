import FicheroAPIClient
import SwiftUI

struct NoteUpdateActionParams: Encodable {
    let noteId: String
    let update: Components.Schemas.NotePatchRequest

    enum CodingKeys: String, CodingKey {
        case noteId = "note_id"
        case update
    }
}

struct NoteDeleteActionParams: Encodable {
    let noteId: String

    enum CodingKeys: String, CodingKey {
        case noteId = "note_id"
    }
}

/// Shared renderer for one note.
struct NoteDetailView: View {
    let item: NoteSelectionItem?

    var onSave: ((NoteSelectionItem, String) async throws -> Void)?
    var onDelete: ((NoteSelectionItem) async throws -> Void)?
    /// Loads a note's backlinks + forward links (#1433). Nil hides the Links
    /// section — used by the torn-off note window, which has no store scope.
    var onLoadLinks: ((String) async -> NoteLinks?)?

    @State private var draftBody = ""
    @State private var draftId: String?
    @State private var isSaving = false
    @State private var errorText: String?
    @State private var links: NoteLinks = .empty
    @State private var isLoadingLinks = false

    var body: some View {
        Group {
            if let item {
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        if let errorText {
                            errorBox(errorText)
                        }
                        headerSection(item)
                        editorSection(item)
                        metadataSection(item)
                        linksSection(item)
                        actionsSection(item)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .frame(maxWidth: .infinity, alignment: .topLeading)
                }
                .onAppear { syncDraft(for: item) }
                .onChange(of: item.id) { _, _ in syncDraft(for: item) }
                .task(id: item.id) { await loadLinks(for: item) }
            } else {
                emptyState
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    @ViewBuilder
    private func headerSection(_ item: NoteSelectionItem) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(item.title)
                .font(.title3.weight(.semibold))
            HStack(spacing: 8) {
                Text(item.kindLabel)
                    .font(.caption)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Capsule().fill(Color.accentColor.opacity(0.12)))
                if let scopeLabel = item.scopeLabel {
                    Text(scopeLabel)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let updatedLabel = item.updatedLabel {
                    Text(updatedLabel)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    @ViewBuilder
    private func editorSection(_ item: NoteSelectionItem) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Content")
                .font(.subheadline.weight(.semibold))
            if onSave != nil {
                TextEditor(text: $draftBody)
                    .font(.body)
                    .frame(minHeight: 180)
                    .overlay(
                        RoundedRectangle(cornerRadius: 6)
                            .stroke(Color.secondary.opacity(0.25), lineWidth: 1)
                    )
            } else {
                Text(item.note.body ?? "No body text")
                    .font(.body)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    @ViewBuilder
    private func metadataSection(_ item: NoteSelectionItem) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Metadata")
                .font(.subheadline.weight(.semibold))
            if let tags = item.note.tags, !tags.isEmpty {
                HStack {
                    ForEach(Array(tags.prefix(6)), id: \.self) { tag in
                        Text("#\(tag)")
                            .font(.caption2)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Capsule().fill(Color.accentColor.opacity(0.12)))
                    }
                    Spacer()
                }
            }
            if let createdAt = item.note.createdAt {
                Text("Created \(createdAt.formatted(date: .abbreviated, time: .shortened))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if let updatedAt = item.note.updatedAt {
                Text("Updated \(updatedAt.formatted(date: .abbreviated, time: .shortened))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private func actionsSection(_ item: NoteSelectionItem) -> some View {
        if onSave != nil || onDelete != nil {
            HStack {
                Spacer()
                if let onDelete {
                    Button(role: .destructive) {
                        Task {
                            await runMutation {
                                try await onDelete(item)
                            }
                        }
                    } label: {
                        Label("Delete", systemImage: "trash")
                    }
                }
                if let onSave {
                    Button {
                        Task {
                            await runMutation {
                                try await onSave(item, draftBody)
                            }
                        }
                    } label: {
                        if isSaving {
                            ProgressView().controlSize(.small)
                        } else {
                            Text("Save")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(draftBody.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSaving)
                }
            }
        }
    }

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "note.text")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No note selected")
                .font(.callout)
            Text("Pick a note from the list to see its details.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.vertical, 32)
    }

    @ViewBuilder
    private func errorBox(_ message: String) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Button("Dismiss") { errorText = nil }
                .buttonStyle(.bordered)
                .controlSize(.small)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.orange.opacity(0.1))
    }

    private func syncDraft(for item: NoteSelectionItem) {
        if draftId != item.id {
            draftId = item.id
            draftBody = item.note.body ?? ""
            errorText = nil
        }
    }

    private func runMutation(_ work: @escaping () async throws -> Void) async {
        isSaving = true
        errorText = nil
        do {
            try await work()
        } catch {
            errorText = error.localizedDescription
        }
        isSaving = false
    }
}

// MARK: - Links (#1433 — Tinderbox-style backlinks + forward links)

private extension NoteDetailView {

    @ViewBuilder
    func linksSection(_ item: NoteSelectionItem) -> some View {
        // Only shown where a loader is provided (the inspector pane, which has the
        // NoteStore). The torn-off note window has no store scope, so it passes
        // nil and this section is hidden.
        if onLoadLinks != nil {
            VStack(alignment: .leading, spacing: 8) {
                Text("Links")
                    .font(.subheadline.weight(.semibold))
                if isLoadingLinks {
                    ProgressView().controlSize(.small)
                } else if links.isEmpty {
                    Text("No linked notes")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    linkGroup("Backlinks", notes: links.backlinks)
                    linkGroup("Forward links", notes: links.forward)
                }
            }
        }
    }

    @ViewBuilder
    func linkGroup(_ title: String, notes: [NoteItem]) -> some View {
        if !notes.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.secondary)
                ForEach(notes) { note in
                    HStack(spacing: 6) {
                        Image(systemName: "note.text")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Text(linkedNoteTitle(note))
                            .font(.caption)
                            .lineLimit(1)
                        Spacer(minLength: 0)
                    }
                }
            }
        }
    }

    /// A linked note's display title: its `title`, else the first line of its
    /// body, else a short id — never blank.
    func linkedNoteTitle(_ note: NoteItem) -> String {
        if let title = note.title, !title.isEmpty { return title }
        if let body = note.body, !body.isEmpty {
            return String(body.prefix(while: { !$0.isNewline }).prefix(80))
        }
        return note.id.map { "Note \($0.prefix(8))" } ?? "Untitled note"
    }

    func loadLinks(for item: NoteSelectionItem) async {
        guard let onLoadLinks, let noteId = item.note.id else {
            links = .empty
            return
        }
        isLoadingLinks = true
        links = await onLoadLinks(noteId) ?? .empty
        isLoadingLinks = false
    }
}
