import SwiftUI

/// Annotations tab for the Document Inspector (#1276), rebuilt as List + detail.
struct DocumentInspectorAnnotationsTab: View {
    let document: Document

    @Environment(AnnotationStore.self) private var annotationStore
    @State private var claimFocusState = ClaimFocusState.shared

    @State private var focused = FocusedAnnotation.shared
    @State private var newNoteText: String = ""
    @State private var searchText: String = ""
    @State private var isAdding = false
    @FocusState private var noteFieldFocused: Bool

    private var filteredAnnotations: [DocumentAnnotation] {
        annotationStore.annotations.filter { AnnotationStore.matchesSearch($0, query: searchText) }
    }

    var body: some View {
        VStack(spacing: 0) {
            addBar
            Divider()
            AnnotationsInspectorPane(
                document: document,
                annotations: filteredAnnotations,
                focused: focused
            )
            annotationFilterBar
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task(id: document.id) {
            await loadAnnotations()
        }
        .accessibilityIdentifier("annotationsTab")
    }

    // MARK: - Add bar

    private var addBar: some View {
        VStack(spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: "note.text.badge.plus")
                    .foregroundStyle(.secondary)
                TextField("Add a note…", text: $newNoteText)
                    .textFieldStyle(.plain)
                    .focused($noteFieldFocused)
                    .onSubmit { addNote() }
                    .accessibilityIdentifier("annotationNoteField")
                Button {
                    addNote()
                } label: {
                    if isAdding {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Add")
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(newNoteText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isAdding)
                .accessibilityIdentifier("annotationAddButton")
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .onChange(of: searchText) { _, _ in
            focused.clear()
        }
    }

    private var annotationFilterBar: some View {
        PaneFilterBar {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.secondary)
            TextField("Search notes, tags, claim id…", text: $searchText)
                .textFieldStyle(.plain)
                .accessibilityIdentifier("annotationSearchField")
            if let claimId = activeClaimId {
                Text("Linked claim: \(claimId)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
    }

    // MARK: - Actions

    private func addNote() {
        let trimmed = newNoteText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !isAdding else { return }
        isAdding = true
        let linkedClaimIds = activeClaimId.map { [$0] } ?? []
        Task {
            let created = await annotationStore.addNote(
                scope: annotationScope,
                text: trimmed,
                linkedClaimIds: linkedClaimIds
            )
            if created != nil { newNoteText = "" }
            isAdding = false
            noteFieldFocused = false
        }
    }

    private func loadAnnotations() async {
        focused.clear()
        focused.documentName = document.name
        await annotationStore.loadAnnotations(for: annotationScope, force: true)
    }

    private var activeClaimId: String? {
        guard claimFocusState.selectedClaimSourceDocumentId == nil
                || claimFocusState.selectedClaimSourceDocumentId == document.id else {
            return nil
        }
        return claimFocusState.selectedClaimId
    }

    private var annotationScope: AnnotationScope {
        switch document.docType {
        case .folder:
            return .folder(document.id)
        case .page:
            return .page(document.id)
        default:
            return .document(document.id)
        }
    }
}
