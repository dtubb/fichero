import FicheroAPIClient
import SwiftUI

/// Notes inspector built as List + detail. Mirrors `CitationsInspectorPane` /
/// `ArtifactsInspectorPane` / `AnnotationsInspectorPane`: a vertical list/detail
/// split that fits the narrow document inspector column.
struct NotesInspectorPane: View {
    let notes: [NoteSelectionItem]
    let selectionResetToken: String
    let documentName: String?

    @Environment(NoteStore.self) private var noteStore
    @Environment(WindowState.self) private var windowState
    @Environment(\.openWindow) private var openWindow
    @Environment(\.supportsMultipleWindows) private var supportsMultipleWindows

    @Bindable var focused: FocusedNote

    private var selectedNote: NoteSelectionItem? {
        focused.id.flatMap { id in notes.first { $0.id == id } }
    }

    var body: some View {
        VStack(spacing: 0) {
            if let loadError = noteStore.loadError {
                errorBox(loadError)
            }
            PlatformVSplitView {
                NoteListView(
                    notes: notes,
                    focused: focused,
                    onOpenInWindow: openDetailWindow
                )
                .frame(minHeight: 140, idealHeight: 180)

                Divider()

                NoteDetailView(
                    item: selectedNote,
                    onSave: { item, body in
                        try await saveNote(item, body: body)
                    },
                    onDelete: { item in
                        try await deleteNote(item)
                    },
                    onLoadLinks: { noteId in
                        try? await noteStore.links(for: noteId)
                    }
                )
                .frame(minHeight: 240, idealHeight: 360)
            }
            Divider()
            InspectorBottomMiniToolbar(statusText: notesToolbarStatusText) {
                Button {
                    Task { await noteStore.reload() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .help("Reload notes")
                .accessibilityLabel("Reload notes")

                Button {
                    openDetailWindow()
                } label: {
                    Image(systemName: "macwindow.badge.plus")
                }
                .buttonStyle(.plain)
                .help("Open the selected note in a separate window")
                .accessibilityLabel("Open selected note in window")
                .disabled(focused.id == nil)
            }
        }
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Button {
                    openDetailWindow()
                } label: {
                    Label("Open in Window", systemImage: "macwindow.badge.plus")
                }
                .help("Open the selected note in a separate window")
                .disabled(focused.id == nil)
            }
        }
        .task(id: selectionResetToken) {
            focused.clear()
            focused.documentName = documentName
        }
        .onChange(of: notes) { _, items in
            focused.resolve(in: items)
        }
    }

    private var notesToolbarStatusText: String {
        if let selectedNote {
            return selectedNote.title
        }
        return "\(notes.count) notes"
    }

    private func openDetailWindow() {
        // No-op on single-window platforms (iPhone) so the button isn't a silent
        // dead affordance (#2805).
        guard supportsMultipleWindows else { return }
        focused.resolve(in: notes)
        openWindow(id: "note-detail")
    }

    private func saveNote(_ item: NoteSelectionItem, body: String) async throws {
        guard let noteId = item.note.id,
              let library = LibraryManager.shared.getLibrary(id: windowState.libraryId) else { return }
        var update = Components.Schemas.NotePatchRequest()
        update.body = body
        let result = try await library.actionsService.invokeAction(
            name: "note.update",
            params: NoteUpdateActionParams(noteId: noteId, update: update)
        )
        LastAction.shared.record(auditId: result.auditId, actionName: "note.update")
        await noteStore.reload()
        focused.resolve(in: noteStore.notes.map(NoteSelectionItem.init))
    }

    private func deleteNote(_ item: NoteSelectionItem) async throws {
        guard let noteId = item.note.id,
              let library = LibraryManager.shared.getLibrary(id: windowState.libraryId) else { return }
        let result = try await library.actionsService.invokeAction(
            name: "note.delete",
            params: NoteDeleteActionParams(noteId: noteId)
        )
        LastAction.shared.record(auditId: result.auditId, actionName: "note.delete")
        if focused.id == item.id {
            focused.clear()
        }
        await noteStore.reload()
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
            Button("Retry") {
                Task { await noteStore.reload() }
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.orange.opacity(0.1))
    }
}

/// The torn-off note-detail window.
struct NoteDetailWindow: View {
    @State private var focused = FocusedNote.shared

    @State private var isPinned = false
    @State private var pinnedItem: NoteSelectionItem?

    private var shownItem: NoteSelectionItem? {
        isPinned ? pinnedItem : focused.item
    }

    var body: some View {
        NoteDetailView(item: shownItem)
            .navigationTitle(shownItem?.title ?? "Note")
            #if !os(visionOS)
            .navigationSubtitle(focused.documentName ?? "")
            #endif
            .toolbar {
                ToolbarItem(placement: .automatic) {
                    Toggle(isOn: $isPinned) {
                        Label(
                            isPinned ? "Pinned" : "Following selection",
                            systemImage: isPinned ? "pin.fill" : "pin"
                        )
                    }
                    .toggleStyle(.button)
                    .help(
                        isPinned
                            ? "Pinned to this note — won't follow selection"
                            : "Following the inspector's selection"
                    )
                    .onChange(of: isPinned) { _, pinned in
                        pinnedItem = pinned ? focused.item : nil
                    }
                }
            }
            .frame(minWidth: 360, minHeight: 320)
    }
}
