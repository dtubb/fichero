import FicheroAPIClient
import SwiftUI

// MARK: - DocumentBibliographyPanel (#1434)

/// Extracted bibliography panel — scholarly references extracted from
/// within the document itself, backed by `GET /api/documents/{id}/citations`.
/// Distinct from CitationGraphPanel (doc-to-doc links in the knowledge
/// graph); this shows the bibliography inside the document itself.
struct DocumentBibliographyPanel: View {
    let documentId: String

    // Live-refresh via the per-document ReferenceStore (#1999): the store owns
    // the fetch + the `reference.*` change-stream reactions. Reading the store's
    // properties in `body` registers the @Observable dependency.
    private var store: ReferenceStore? { LibraryManager.shared.globalLibrary?.referenceStore }
    private var references: [Components.Schemas.Reference] { store?.references ?? [] }
    private var selfRef: Components.Schemas.Reference? { store?.selfRef }
    private var isLoading: Bool { store?.isLoading ?? false }
    private var loadError: String? { store?.loadError }
    @State private var copiedAll = false
    // Reference pending a confirmed delete (#3258 — surfaces the undoable
    // reference delete the action layer already backs).
    @State private var pendingDelete: Components.Schemas.Reference?
    @State private var deleteError: String?
    // Bibliography extractor trigger (#3258) — the endpoint existed unused.
    @State private var isExtracting = false
    @State private var extractError: String?

    private var allBibtex: String {
        let parts = ([selfRef].compactMap { $0 } + references)
            .compactMap { $0.bibtex }
            .filter { !$0.isEmpty }
        return parts.joined(separator: "\n\n")
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
                        Task { await store?.setScope(documentId: documentId, force: true) }
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
        .task(id: documentId) { await store?.setScope(documentId: documentId) }
        .confirmationDialog(
            pendingDelete.map { "Delete \"\(referenceTitle($0))\"?" } ?? "Delete reference?",
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
                        try await store?.deleteReference(id)
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
            isPresented: Binding(
                get: { deleteError != nil },
                set: { if !$0 { deleteError = nil } }
            )
        ) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(deleteError ?? "")
        }
        .alert(
            "Couldn't extract bibliography",
            isPresented: Binding(
                get: { extractError != nil },
                set: { if !$0 { extractError = nil } }
            )
        ) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(extractError ?? "")
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
                try await store?.runExtractor()
            } catch {
                extractError = error.localizedDescription
            }
        }
    }

    @ViewBuilder
    private func referenceRow(_ ref: Components.Schemas.Reference, isSelf: Bool) -> some View {
        // Only the cited references are deletable; the document's own entry
        // (isSelf) is not a bibliography row to remove.
        ReferenceRowView(
            ref: ref,
            isSelf: isSelf,
            onDelete: (isSelf || ref.id == nil) ? nil : { pendingDelete = ref }
        )
    }
}

private struct ReferenceRowView: View {
    let ref: Components.Schemas.Reference
    let isSelf: Bool
    /// Present only for deletable rows (#3258); nil disables the delete action.
    var onDelete: (() -> Void)?

    @State private var isExpanded = false
    @State private var copied = false

    var body: some View {
        rowContent
            .contextMenu {
                if let onDelete {
                    Button("Delete Reference…", role: .destructive, action: onDelete)
                }
            }
    }

    private var rowContent: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                if isSelf {
                    Image(systemName: "doc.text")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Text(refTitle)
                    .font(.caption)
                    .foregroundStyle(.primary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 4)
                if let bibtex = ref.bibtex, !bibtex.isEmpty {
                    Button {
                        if isExpanded {
                            PlatformPasteboard.writeString(bibtex)
                            copied = true
                        } else {
                            isExpanded = true
                        }
                    } label: {
                        Image(systemName: copied ? "checkmark" : (isExpanded ? "doc.on.doc" : "chevron.down"))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help(isExpanded ? "Copy BibTeX" : "Show BibTeX")
                    .onChange(of: copied) { _, newValue in
                        if newValue {
                            Task {
                                try? await Task.sleep(for: .seconds(1.5))
                                copied = false
                            }
                        }
                    }
                }
            }
            HStack(spacing: 6) {
                if let authors = ref.authors, !authors.isEmpty {
                    Text(authors.prefix(2).joined(separator: ", "))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                if let year = ref.year {
                    Text(String(year))
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.tertiary)
                }
                if let doi = ref.doi, !doi.isEmpty {
                    Text("DOI")
                        .font(.caption2)
                        .foregroundStyle(Color.accentColor)
                        .help(doi)
                }
                Spacer(minLength: 4)
                if let journal = ref.journalOrBook {
                    Text(journal)
                        .font(.caption2)
                        .italic()
                        .foregroundStyle(.tertiary)
                        .lineLimit(1)
                }
            }
            if isExpanded, let bibtex = ref.bibtex, !bibtex.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    Text(bibtex)
                        .font(.system(.caption2, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                        .padding(6)
                        .background(Color(.textBackgroundColor).opacity(0.6))
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                }
                .frame(maxHeight: 80)
            }
        }
        .padding(.vertical, 2)
    }

    private var refTitle: String {
        if let title = ref.title, !title.isEmpty { return title }
        if let bib = ref.bibtex, !bib.isEmpty { return String(bib.prefix(60)) + "…" }
        return "Untitled"
    }
}
