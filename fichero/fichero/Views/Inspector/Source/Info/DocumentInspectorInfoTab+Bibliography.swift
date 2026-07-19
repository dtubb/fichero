import FicheroAPIClient
import SwiftUI

// MARK: - DocumentBibliographyPanel (#1434)
//
// The bibliography row (`ReferenceRowView`) and edit sheet (`ReferenceEditSheet`)
// live in sibling files: DocumentInspectorInfoTab+BibliographyRow.swift and
// DocumentInspectorInfoTab+ReferenceEditSheet.swift.

/// Extracted bibliography panel — scholarly references extracted from
/// within the document itself, backed by `GET /api/documents/{id}/citations`.
/// Distinct from CitationGraphPanel (doc-to-doc links in the knowledge
/// graph); this shows the bibliography inside the document itself.
struct DocumentBibliographyPanel: View {
    let documentId: String
    @Environment(ReferenceStore.self) private var store

    // Live-refresh via the per-document ReferenceStore (#1999): the store owns
    // the fetch + the `reference.*` change-stream reactions. Reading the store's
    // properties in `body` registers the @Observable dependency.
    private var references: [Components.Schemas.Reference] { store.references }
    private var selfRef: Components.Schemas.Reference? { store.selfRef }
    private var isLoading: Bool { store.isLoading }
    private var loadError: String? { store.loadError }
    @State private var copiedAll = false
    // Reference pending a confirmed delete (#3258 — surfaces the undoable
    // reference delete the action layer already backs).
    @State private var pendingDelete: Components.Schemas.Reference?
    @State private var deleteError: String?
    // Bibliography extractor trigger (#3258) — the endpoint existed unused.
    @State private var isExtracting = false
    @State private var extractError: String?
    // Reference being edited (#3258) — surfaces the undoable metadata PATCH.
    @State private var editing: EditingReference?
    // References whose DOI/ISBN resolve is in flight (#3258), + last error.
    @State private var resolvingIds: Set<String> = []
    @State private var resolveError: String?

    private var allBibtex: String {
        let parts = ([selfRef].compactMap { $0 } + references)
            .compactMap { $0.bibtex }
            .filter { !$0.isEmpty }
        return parts.joined(separator: "\n\n")
    }

    private var deleteDialogTitle: String {
        pendingDelete.map { "Delete \"\(referenceTitle($0))\"?" } ?? "Delete reference?"
    }

    private var deleteErrorMessage: String { deleteError ?? "" }
    private var extractErrorMessage: String { extractError ?? "" }
    private var resolveErrorMessage: String { resolveError ?? "" }

    private var isShowingDeleteError: Binding<Bool> {
        Binding(
            get: { deleteError != nil },
            set: { if !$0 { deleteError = nil } }
        )
    }

    private var isShowingExtractError: Binding<Bool> {
        Binding(
            get: { extractError != nil },
            set: { if !$0 { extractError = nil } }
        )
    }

    private var isShowingResolveError: Binding<Bool> {
        Binding(
            get: { resolveError != nil },
            set: { if !$0 { resolveError = nil } }
        )
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if isLoading && references.isEmpty && loadError == nil {
                HStack(spacing: 6) {
                    ProgressView().scaleEffect(0.6)
                    Text("Loading…").font(.caption).foregroundStyle(.secondary)
                }
            } else if let err = loadError {
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.caption).foregroundStyle(.orange)
                    Text(err)
                        .font(.caption).foregroundStyle(.secondary)
                    Spacer(minLength: 0)
                    Button("Retry") {
                        Task { await store.setScope(documentId: documentId, force: true) }
                    }
                        .font(.caption2).buttonStyle(.borderless)
                }
            } else if references.isEmpty && selfRef == nil {
                VStack(alignment: .leading, spacing: 8) {
                    Text("No bibliography extracted yet.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Button {
                        runExtractor()
                    } label: {
                        if isExtracting {
                            HStack(spacing: 6) {
                                ProgressView().scaleEffect(0.6)
                                Text("Extracting…")
                            }
                            .font(.caption)
                        } else {
                            Label("Extract bibliography", systemImage: "text.book.closed")
                                .font(.caption)
                        }
                    }
                    .buttonStyle(.borderless)
                    .disabled(isExtracting)
                }
            } else {
                if !allBibtex.isEmpty {
                    HStack {
                        Spacer()
                        Button {
                            PlatformPasteboard.writeString(allBibtex)
                            copiedAll = true
                        } label: {
                            Label(
                                copiedAll ? "Copied!" : "Copy all BibTeX",
                                systemImage: copiedAll ? "checkmark" : "doc.on.doc"
                            )
                            .font(.caption2)
                        }
                        .buttonStyle(.plain)
                        .foregroundStyle(.secondary)
                        .onChange(of: copiedAll) { _, newValue in
                            if newValue {
                                Task {
                                    try? await Task.sleep(for: .seconds(1.5))
                                    copiedAll = false
                                }
                            }
                        }
                    }
                }
                if let selfRef {
                    referenceRow(selfRef, isSelf: true)
                    if !references.isEmpty { Divider() }
                }
                LazyVStack(alignment: .leading, spacing: 6) {
                    ForEach(references, id: \.id) { ref in
                        referenceRow(ref, isSelf: false)
                    }
                }
            }
        }
        .task(id: documentId) { await store.setScope(documentId: documentId) }
        .confirmationDialog(
            deleteDialogTitle,
            isPresented: Binding(
                get: { pendingDelete != nil },
                set: { if !$0 { pendingDelete = nil } }
            ),
            presenting: pendingDelete
        ) { ref in
            Button("Delete Reference", role: .destructive) {
                guard let id = ref.id else { return }
                Task {
                    do {
                        try await store.deleteReference(id)
                    } catch {
                        deleteError = error.localizedDescription
                    }
                }
            }
            Button("Cancel", role: .cancel) {}
        } message: { _ in
            Text("Removes this reference from the library bibliography. This can be undone.")
        }
        .alert(
            "Couldn't delete reference",
            isPresented: isShowingDeleteError
        ) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(deleteErrorMessage)
        }
        .alert(
            "Couldn't extract bibliography",
            isPresented: isShowingExtractError
        ) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(extractErrorMessage)
        }
        .alert(
            "Couldn't resolve reference",
            isPresented: isShowingResolveError
        ) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(resolveErrorMessage)
        }
        .sheet(item: $editing) { editing in
            ReferenceEditSheet(reference: editing.ref) { patch in
                try await store.patchReference(editing.id, patch: patch)
            }
        }
    }

    private func referenceTitle(_ ref: Components.Schemas.Reference) -> String {
        if let title = ref.title, !title.isEmpty { return title }
        return "reference"
    }

    private func runExtractor() {
        isExtracting = true
        Task { @MainActor in
            defer { isExtracting = false }
            do {
                try await store.runExtractor()
            } catch {
                extractError = error.localizedDescription
            }
        }
    }

    private func resolve(_ ref: Components.Schemas.Reference) {
        guard let id = ref.id, !resolvingIds.contains(id) else { return }
        resolvingIds.insert(id)
        Task { @MainActor in
            defer { resolvingIds.remove(id) }
            do {
                try await store.resolveReference(doi: ref.doi, isbn: ref.isbn)
            } catch {
                resolveError = error.localizedDescription
            }
        }
    }

    @ViewBuilder
    private func referenceRow(_ ref: Components.Schemas.Reference, isSelf: Bool) -> some View {
        // Only the cited references are deletable; the document's own entry
        // (isSelf) is not a bibliography row to remove.
        let editable = !isSelf && ref.id != nil
        let hasIdentifier = !(ref.doi ?? "").isEmpty || !(ref.isbn ?? "").isEmpty
        ReferenceRowView(
            ref: ref,
            isSelf: isSelf,
            isResolving: ref.id.map { resolvingIds.contains($0) } ?? false,
            onEdit: editable ? { if let id = ref.id { editing = EditingReference(id: id, ref: ref) } } : nil,
            onResolve: (editable && hasIdentifier) ? { resolve(ref) } : nil,
            onDelete: editable ? { pendingDelete = ref } : nil
        )
    }
}

/// Identifiable wrapper so a `Reference` (whose `id` is optional) can drive
/// `.sheet(item:)`. Only built for references that have an id.
private struct EditingReference: Identifiable {
    let id: String
    let ref: Components.Schemas.Reference
}
