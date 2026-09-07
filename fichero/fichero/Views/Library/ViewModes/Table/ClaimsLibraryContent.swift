import FicheroAPIClient
import SwiftUI

// MARK: - Claims library content (folder-scoped claims as a table)

/// Hosts the claims table inside the library: loads the folder's claims, builds
/// the rows, applies the library's active search text, and wires a row click to
/// the shared source cursor. Self-contained so the huge `LibraryView` only has to
/// route to it — everything claim-specific lives here and in the small pure
/// helpers (`LibraryClaimsModel`, `ClaimTableRow`, `ClaimsTableView`).
struct ClaimsLibraryContent: View {
    /// The folder to scope to; `nil` is library-wide (the Phase-3 sidebar path).
    let folderId: String?
    let entityService: EntityService
    /// The currently-loaded documents, used to resolve a claim's source page to a
    /// human name (never a raw id).
    let documents: [Document]
    /// The library's active ⌘F query, so the claims table narrows with the same
    /// search box as every other mode.
    let searchQuery: String?
    @Binding var selection: Set<String>

    /// The SHARED source cursor — a claim row opens its page + highlight through
    /// the same seam the claim card and entity biography use. Optional → safe
    /// no-op without a host.
    @Environment(ClaimSourceNavigationState.self) private var cursor: ClaimSourceNavigationState?

    @State private var model: LibraryClaimsModel?

    var body: some View {
        ClaimsTableView(
            items: items,
            selection: $selection,
            isLoading: model?.isLoading ?? true,
            emptyMessage: emptyMessage,
            onOpenSource: openSource
        )
        .task(id: folderId) {
            let active = model ?? LibraryClaimsModel(service: entityService)
            model = active
            await active.load(folderId: folderId)
        }
    }

    private var emptyMessage: String {
        if let error = model?.loadError {
            return "Couldn't load claims: \(error)"
        }
        if let query = trimmedQuery {
            return "No claims match “\(query)”."
        }
        return "No claims here yet. Run knowledge extraction to populate them."
    }

    private var trimmedQuery: String? {
        let q = (searchQuery ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return q.isEmpty ? nil : q
    }

    /// Resolve claims → sortable rows, filtered by the active search text over the
    /// claim's own words and its source page name.
    private var items: [ClaimsTableView.Item] {
        let docsById = Dictionary(documents.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let needle = trimmedQuery?.lowercased()

        return (model?.claims ?? []).compactMap { claim -> ClaimsTableView.Item? in
            let values = ClaimTableRow(claim)
            let sourceName = Self.sourceName(for: claim.sourceDocumentId, docsById: docsById)
            if let needle {
                let haystack = "\(values.svoLine) \(values.date) \(sourceName)".lowercased()
                guard haystack.contains(needle) else { return nil }
            }
            // Reuse the outline's claim-node identity so a claim selects the same
            // whether it appears here or as a document's disclosed child. Parent is
            // the source document when loaded, else a minimal stand-in carrying the
            // id (the node id is "<sourceDoc>:claim:<claimId>", still unique).
            let parent = docsById[claim.sourceDocumentId ?? ""]
                ?? Document(id: claim.sourceDocumentId ?? "unknown", name: sourceName)
            return ClaimsTableView.Item(
                node: LibraryOutlineNode.claimItem(claim, parent: parent),
                claim: claim,
                values: values,
                sourceName: sourceName
            )
        }
    }

    /// A claim row opens its source page with the passage lit, through the shared
    /// cursor — reusing `ClaimSourceRequest` (no new nav path). A claim with no
    /// honest destination simply doesn't navigate.
    private func openSource(_ claim: Components.Schemas.KnowledgeClaim) {
        guard let request = ClaimSourceRequest.request(for: claim) else { return }
        cursor?.request(request)
    }

    /// Human name for a claim's source document — its page title when the document
    /// is loaded, else a short, non-raw placeholder (never the 32-char id).
    static func sourceName(for docId: String?, docsById: [String: Document]) -> String {
        guard let docId, !docId.isEmpty else { return "—" }
        if let doc = docsById[docId] {
            let parent = doc.parentId.flatMap { docsById[$0] }
            return DocumentTitle.displayName(for: doc, parent: parent)
        }
        return "Source \(docId.prefix(8))…"
    }
}
