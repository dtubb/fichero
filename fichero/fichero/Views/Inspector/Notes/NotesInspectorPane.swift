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
    @Environment(\.openWindow) private var openWindow
    @Environment(\.supportsMultipleWindows) private var supportsMultipleWindows

    @Bindable var focused: FocusedNote

    /// A save refused because another Mac edited the note first (#5348): the person picks whose text wins.
    @State private var staleSave: (noteId: String, body: String)?
    /// Why the last Keep mine did not save; shown in the dialog that comes back with the text still held.
    @State private var staleRetryError: String?
    /// Both texts shown side by side while the person decides (#5348); the dialog returns when it closes.
    @State private var comparing: NoteStaleComparison?
    /// The save under comparison, held apart from `staleSave` so the dialog and the sheet never show together.
    @State private var comparePending: (noteId: String, body: String)?
    /// A plain sentence above the list, e.g. the note was deleted elsewhere and the text was copied.
    @State private var notice: String?

    private var selectedNote: NoteSelectionItem? {
        focused.id.flatMap { id in notes.first { $0.id == id } }
    }

    var body: some View {
        VStack(spacing: 0) {
            if let loadError = noteStore.loadError {
                errorBox(loadError)
            }
            if let notice {
                errorBox(notice)
            }
            InspectorListDetailSplit {
                NoteListView(
                    notes: notes,
                    focused: focused,
                    onOpenInWindow: openDetailWindow
                )
            } detail: {
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
                    },
                    // #4502: following a link is just selecting that note in
                    // the list beside it — the detail pane follows the same
                    // `focused.id` it already follows, so there is no second
                    // navigation path to keep in step. The torn-off window
                    // (`:154`) passes nothing and its links stay plain text,
                    // because it has no list to select in.
                    onOpenLink: { noteId in focused.id = noteId }
                )
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
        .confirmationDialog(
            "This note was changed on another Mac",
            isPresented: Binding(get: { staleSave != nil }, set: { if !$0 { staleSave = nil } }),
            titleVisibility: .visible
        ) {
            // The dialog clears `staleSave` as it closes, so each button hands the text over now.
            Button("Keep mine") { if let held = staleSave { Task { await resolveStale(pending: held, keepMine: true) } } }
            Button("Take theirs") { if let held = staleSave { Task { await resolveStale(pending: held, keepMine: false) } } }
            Button("Compare") { if let held = staleSave { Task { await compareStale(held) } } }
            Button("Cancel", role: .cancel) { staleSave = nil }
        } message: {
            Text(staleRetryError
                ?? "Nothing was saved. Keep your text, compare the two, or take theirs (your text is copied to the clipboard).")
        }
        .sheet(item: $comparing, onDismiss: {
            // Closed without choosing: the text comes back in the dialog, never lost.
            if let held = comparePending { staleSave = held }
            comparePending = nil
        }, content: { comparison in
            NoteStaleCompareView(comparison: comparison) { keepMine in
                guard let held = comparePending else { return }
                comparePending = nil
                comparing = nil
                Task { await resolveStale(pending: held, keepMine: keepMine) }
            }
        })
    }

    private func compareStale(_ pending: (noteId: String, body: String)) async {
        await noteStore.reload()
        let theirs = noteStore.notes.first(where: { $0.id == pending.noteId })?.body ?? nil
        comparing = NoteStaleResolution.comparison(mine: pending.body, theirs: theirs)
        if comparing == nil {
            notice = "This note was deleted on another Mac."
        } else {
            comparePending = pending
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

    // Mutations route through the injected NoteStore — the sanctioned observable
    // data layer — instead of resolving an action service through LibraryManager
    // + WindowState (#3430). The store reloads its published `notes` internally.
    private func saveNote(_ item: NoteSelectionItem, body: String) async throws {
        guard let noteId = item.note.id else { return }
        notice = nil
        do {
            _ = try await noteStore.update(noteId: noteId, body: body, expectedUpdatedAt: item.note.updatedAt)
        } catch NoteServiceError.stale {
            // Deleted on the other Mac: that delete wins here, so no dialog and nothing to keep.
            await noteStore.reload()
            if noteStore.notes.contains(where: { $0.id == noteId }) {
                staleSave = (noteId, body)
            } else {
                notice = "This note was deleted on another Mac."
            }
        }
        focused.resolve(in: noteStore.notes.map(NoteSelectionItem.init))
    }

    /// Keep mine: read the current version, then save my text against it. A retry that fails never drops
    /// the text: stale again or any other error brings the dialog back with it. Take theirs: read theirs,
    /// after copying the dropped text to the clipboard so it is not lost.
    private func resolveStale(pending: (noteId: String, body: String), keepMine: Bool) async {
        staleSave = nil
        staleRetryError = nil
        await noteStore.reload()
        let current = noteStore.notes.first(where: { $0.id == pending.noteId })
        switch NoteStaleResolution.decide(keepMine: keepMine, currentUpdatedAt: current?.updatedAt) {
        case .saveAgainst(let version):
            do {
                _ = try await noteStore.update(noteId: pending.noteId, body: pending.body, expectedUpdatedAt: version)
            } catch NoteServiceError.stale {
                staleSave = pending
            } catch {
                staleRetryError = "Saving failed: \(error.localizedDescription)"
                staleSave = pending
            }
        case .deletedElsewhere:
            notice = "This note was deleted on another Mac."
        case .copyAndTakeTheirs:
            PlatformPasteboard.writeString(pending.body)
        }
        focused.resolve(in: noteStore.notes.map(NoteSelectionItem.init))
    }

    private func deleteNote(_ item: NoteSelectionItem) async throws {
        guard let noteId = item.note.id else { return }
        try await noteStore.delete(noteId: noteId)
        if focused.id == item.id {
            focused.clear()
        }
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
