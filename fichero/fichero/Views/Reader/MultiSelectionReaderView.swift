import SwiftUI

// MARK: - Multi-selection reader (Daniel, 2026-08-23: with three cards
// selected "the reader should show them … archival order + headers"). The
// reading pane used to show a PaneEmptyStateView for N > 1 — honest about not
// misattributing one item's text, but empty. This renders EVERY selected
// document's transcript in document (archival) order, each under a pinned
// header naming it, so the selection reads as one continuous run of sources.

/// The ids whose transcript must be fetched: the grid's listings hold records
/// shallowly (text-off-parents; page_content never loads with a folder
/// listing), so any selected document without text in hand needs one fetch.
/// File scope so Swift Testing can call it off-main.
func multiReaderMissingTextIds(_ documents: [Document]) -> [String] {
    documents.filter { ($0.pageContent ?? "").isEmpty }.map(\.id)
}

/// The one parent when EVERY selected document is a SECTION of the same
/// parent — a page child, or a region node carrying `regionInParent` (a
/// diary entry, a segment; Daniel 2026-08-29: regions ride the same WebKit
/// renderer) — the case the shared transcript can render directly via its
/// `?pages=` filter (2026-08-25: "we already have the WebKit renderer; it's
/// just telling it what to render"). Mixed selections (across parents, or
/// containing non-sections) return nil and fall back to the native list.
func multiReaderCommonPageParent(_ documents: [Document]) -> String? {
    func isSection(_ doc: Document) -> Bool {
        doc.docType == .page || doc.regionInParent != nil
    }
    guard let first = documents.first, isSection(first),
          let parentId = first.parentId else { return nil }
    let allSameParentSections = documents.allSatisfy {
        isSection($0) && $0.parentId == parentId
    }
    return allSameParentSections ? parentId : nil
}

struct MultiSelectionReaderView: View {
    /// Archival (document) order — `previewStackDocuments` already resolves
    /// selection→documents in listing order; this view never re-sorts.
    let documents: [Document]

    @Environment(DocumentStore.self) private var documentStore
    /// id → decoded transcript. Seeded from the snapshot, replaced by fresh
    /// fetches; absence after load means the document has no transcript.
    @State private var texts: [String: String] = [:]
    @State private var isLoading = true

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0, pinnedViews: [.sectionHeaders]) {
                ForEach(documents) { doc in
                    Section {
                        transcriptBody(for: doc)
                    } header: {
                        sectionHeader(for: doc)
                    }
                }
            }
            .padding(.bottom, 24)
        }
        .background(Color(.textBackgroundColor))
        .task(id: documents.map(\.id).joined(separator: "|")) { await loadTexts() }
        .accessibilityIdentifier("multiSelectionReader")
    }

    @ViewBuilder
    private func sectionHeader(for doc: Document) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "doc.text")
                .foregroundStyle(.secondary)
            Text(DocumentTitle.displayName(for: doc))
                .font(.headline)
            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(.bar)
    }

    @ViewBuilder
    private func transcriptBody(for doc: Document) -> some View {
        if let text = texts[doc.id], !text.isEmpty {
            Text(text)
                .font(.body)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
        } else {
            Text(isLoading ? "Loading…" : "No transcript")
                .font(.callout)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
        }
    }

    private func loadTexts() async {
        isLoading = true
        var next: [String: String] = [:]
        for doc in documents {
            if let content = doc.pageContent, !content.isEmpty {
                next[doc.id] = ArtifactRichTextCodec.plainText(content)
            }
        }
        texts = next
        let missing = multiReaderMissingTextIds(documents)
        for fresh in await documentStore.freshDocuments(ids: missing) {
            if let content = fresh.pageContent, !content.isEmpty {
                texts[fresh.id] = ArtifactRichTextCodec.plainText(content)
            }
        }
        isLoading = false
    }
}
