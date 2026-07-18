import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "NotesBrowserView")

/// Standalone notes browser (#1500), rebuilt as List + detail.
struct NotesBrowserView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(NoteStore.self) private var noteStore

    @State private var focused = FocusedNote.shared
    @State private var kindFilter: String = ""
    @State private var tagFilter: String = ""
    @State private var searchText: String = ""
    @State private var newText = ""
    @State private var newKind = "zettel"
    @State private var isSaving = false

    /// NoteKind raw values, mirrored from the backend enum (#917).
    private let kinds = ["zettel", "reference", "hub", "inbox", "fleeting", "permanent"]

    private var noteItems: [NoteSelectionItem] {
        noteStore.notes.map(NoteSelectionItem.init)
    }

    private var filteredItems: [NoteSelectionItem] {
        noteItems.filter { item in
            if !kindFilter.isEmpty, item.note.kind?.rawValue != kindFilter { return false }
            if !tagFilter.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                let tag = tagFilter.trimmingCharacters(in: .whitespacesAndNewlines)
                guard (item.note.tags ?? []).contains(tag) else { return false }
            }
            if !searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                let needle = searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                let haystack = [
                    item.title,
                    item.bodyPreview,
                    item.kindLabel,
                    item.scopeLabel ?? "",
                    item.tagsLabel ?? ""
                ]
                .joined(separator: " ")
                .lowercased()
                if !haystack.contains(needle) { return false }
            }
            return true
        }
    }

    private var selectionResetToken: String {
        [kindFilter, tagFilter, searchText].joined(separator: "|")
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            filterBar
            Divider()
            addBar
            Divider()
            NotesInspectorPane(
                notes: filteredItems,
                selectionResetToken: selectionResetToken,
                documentName: "Notes",
                focused: focused
            )
        }
        .frame(minWidth: 520, minHeight: 560)
        .task { await reload() }
        .onChange(of: kindFilter) { _, _ in Task { await reload() } }
        .onChange(of: tagFilter) { _, _ in Task { await reload() } }
        .onChange(of: searchText) { _, _ in Task { await reload() } }
    }

    // MARK: - Header

    private var header: some View {
        HStack {
            Text("Notes")
                .font(.headline)
            if !noteStore.isLoading {
                Text("\(noteStore.notes.count)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 1)
                    .background(Capsule().fill(Color(platformColor: .platformQuaternaryLabel).opacity(0.3)))
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

    // MARK: - Actions

    private func reload() async {
        await noteStore.loadAll(kind: kindFilter, tag: tagFilter, query: searchText, force: true)
    }

    private func submitNew() {
        let trimmed = newText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        isSaving = true
        Task {
            do {
                _ = try await noteStore.createFree(body: trimmed, kind: newKind)
                newText = ""
            } catch {
                logger.error("create free note failed: \(error.localizedDescription)")
            }
            isSaving = false
        }
    }
}
