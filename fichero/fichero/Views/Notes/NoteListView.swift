import SwiftUI

/// A native `List(selection:)` of notes.
struct NoteListView: View {
    @Environment(NoteStore.self) private var noteStore
    let notes: [NoteSelectionItem]

    @Bindable var focused: FocusedNote

    var onOpenInWindow: (() -> Void)?
    @State private var selectedNoteIds: Set<String> = []
    @State private var notesToDelete: [NoteSelectionItem] = []
    @State private var showingDeleteConfirmation = false

    private var sortedNotes: [NoteSelectionItem] {
        notes.sorted { lhs, rhs in
            let lhsDate = lhs.note.updatedAt ?? lhs.note.createdAt ?? .distantPast
            let rhsDate = rhs.note.updatedAt ?? rhs.note.createdAt ?? .distantPast
            return lhsDate > rhsDate
        }
    }

    var body: some View {
        List(selection: $selectedNoteIds) {
            ForEach(sortedNotes) { item in
                row(for: item)
                    .tag(item.id)
                    .contextMenu {
                        if let onOpenInWindow {
                            Button("Open in Window") {
                                focused.select(item.id, in: notes)
                                onOpenInWindow()
                            }
                        }
                        Button(role: .destructive) {
                            if selectedNoteIds.contains(item.id) {
                                promptDeleteSelectedNotes()
                            } else {
                                confirmDelete([item])
                            }
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                    }
            }
        }
        .listStyle(.inset)
        .overlay {
            if notes.isEmpty {
                emptyState
            }
        }
        .onChange(of: focused.id) { _, _ in
            if focused.id == nil {
                selectedNoteIds.removeAll()
                focused.clear()
            } else {
                if let focusedId = focused.id {
                    selectedNoteIds = [focusedId]
                }
                focused.resolve(in: notes)
            }
        }
        .onChange(of: selectedNoteIds) { _, newValue in
            focused.id = newValue.first
            focused.resolve(in: notes)
        }
        .onChange(of: notes) { _, items in
            let validIds = Set(items.map(\.id))
            selectedNoteIds = selectedNoteIds.intersection(validIds)
            if let focusedId = focused.id, validIds.contains(focusedId) {
                selectedNoteIds = [focusedId]
            }
            focused.resolve(in: items)
        }
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Button(role: .destructive) {
                    promptDeleteSelectedNotes()
                } label: {
                    Label("Delete Selection", systemImage: "trash")
                }
                .disabled(selectedNoteIds.isEmpty)
            }
        }
        #if os(macOS)
        .onDeleteCommand(perform: promptDeleteSelectedNotes)
        #endif
        .alert("Delete Notes?", isPresented: $showingDeleteConfirmation) {
            Button("Cancel", role: .cancel) {
                notesToDelete = []
            }
            Button("Delete", role: .destructive) {
                let selection = notesToDelete
                if !selection.isEmpty {
                    Task { await deleteSelectedNotes(selection) }
                }
            }
        } message: {
            if notesToDelete.count == 1, let item = notesToDelete.first {
                Text("Are you sure you want to delete \"\(item.title)\"? This action cannot be undone.")
            } else if !notesToDelete.isEmpty {
                Text("Are you sure you want to delete \(notesToDelete.count) notes? This action cannot be undone.")
            }
        }
    }

    @ViewBuilder
    private func row(for item: NoteSelectionItem) -> some View {
        NoteRow(item: item)
            .contentShape(Rectangle())
    }

    private func promptDeleteSelectedNotes() {
        let selection = notes.filter { selectedNoteIds.contains($0.id) }
        guard !selection.isEmpty else { return }
        confirmDelete(selection)
    }

    private func confirmDelete(_ selection: [NoteSelectionItem]) {
        notesToDelete = selection
        showingDeleteConfirmation = !selection.isEmpty
    }

    private func deleteSelectedNotes(_ selection: [NoteSelectionItem]) async {
        let ids = selection.compactMap { $0.note.id }
        guard !ids.isEmpty else { return }
        do {
            for noteId in ids {
                try await noteStore.delete(noteId: noteId)
            }
            let deletedIds = Set(selection.map(\.id))
            selectedNoteIds.subtract(deletedIds)
            if let focusedId = focused.id, deletedIds.contains(focusedId) {
                focused.clear()
            }
            notesToDelete = []
            showingDeleteConfirmation = false
        } catch {
            // Keep the selection in place so the user can retry from the same rows.
        }
    }

    private var emptyState: some View {
        // Standardized on ContentUnavailableView (#3039).
        ContentUnavailableView(
            "No notes",
            systemImage: "note.text",
            description: Text("Add a note, or adjust the filters.")
        )
    }
}

private struct NoteRow: View {
    let item: NoteSelectionItem

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: kindIcon)
                .foregroundStyle(.secondary)
                .frame(width: 18)
            VStack(alignment: .leading, spacing: 3) {
                Text(item.title)
                    .font(.body)
                    .lineLimit(2)
                Text(item.bodyPreview)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
                if let metadata = metadataLine {
                    Text(metadata)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 0)
            if let updatedLabel = item.updatedLabel {
                Text(updatedLabel)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
    }

    private var metadataLine: String? {
        var parts: [String] = [item.kindLabel]
        if let scopeLabel = item.scopeLabel { parts.append(scopeLabel) }
        if let tags = item.tagsLabel { parts.append(tags) }
        return parts.joined(separator: " · ")
    }

    private var kindIcon: String {
        switch item.note.kind?.rawValue {
        case "reference":
            return "quote.bubble"
        case "hub":
            return "network"
        case "inbox":
            return "tray"
        case "fleeting":
            return "sparkles"
        case "permanent":
            return "bookmark"
        default:
            return "note.text"
        }
    }
}
