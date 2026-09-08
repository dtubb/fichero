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

    /// Per-table filter (spec: kg-tables, filter.text / filter.claim-type). Intersects
    /// with the shared ⌘F `searchQuery`; empty text + nil type = no per-table filter.
    @State private var filterText = ""
    @State private var filterType: String?

    var body: some View {
        VStack(spacing: 0) {
            filterBar
            ClaimsTableView(
                items: items,
                selection: $selection,
                isLoading: model?.isLoading ?? true,
                emptyMessage: emptyMessage,
                onOpenSource: openSource,
                onDelete: deleteClaims
            )
        }
        .task(id: folderId) {
            let active = model ?? LibraryClaimsModel(service: entityService)
            model = active
            await active.load(folderId: folderId)
        }
    }

    /// Whether a claim row survives the combined filter — the shared search AND the
    /// per-table text AND the type picker must all pass (intersection). Pure so the
    /// rule is testable without a rendered table. (spec: kg-tables,
    /// filter.combines-with-search)
    static func claimMatches(
        haystack: String,
        type: String,
        search: String?,
        filterText: String,
        filterType: String?
    ) -> Bool {
        let hay = haystack.lowercased()
        if let search, !search.isEmpty, !hay.contains(search.lowercased()) { return false }
        let text = filterText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if !text.isEmpty, !hay.contains(text) { return false }
        if let filterType, !filterType.isEmpty,
           type.lowercased() != filterType.lowercased() { return false }
        return true
    }

    /// The claim types present in the loaded set, for the type picker.
    private var availableTypes: [String] {
        Array(Set((model?.claims ?? []).compactMap { $0.claimType?.rawValue })).sorted()
    }

    @ViewBuilder
    private var filterBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "line.3.horizontal.decrease.circle")
                .foregroundStyle(.secondary)
            TextField("Filter claims", text: $filterText)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 220)
            Menu {
                Button("All types") { filterType = nil }
                Divider()
                ForEach(availableTypes, id: \.self) { type in
                    Button(type.capitalized) { filterType = type }
                }
            } label: {
                Label(filterType?.capitalized ?? "All types", systemImage: "tag")
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            Spacer()
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
    }

    private var emptyMessage: String {
        if let error = model?.loadError {
            return "Couldn't load claims: \(error)"
        }
        if let query = trimmedQuery, filterText.isEmpty, filterType == nil {
            return "No claims match “\(query)”."
        }
        if trimmedQuery != nil || !filterText.isEmpty || filterType != nil {
            return "No claims match the current filter."
        }
        return "No claims here yet. Run knowledge extraction to populate them."
    }

    private var trimmedQuery: String? {
        let trimmed = (searchQuery ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    /// Resolve claims → sortable rows, filtered by the active search text over the
    /// claim's own words and its source page name.
    private var items: [ClaimsTableView.Item] {
        let docsById = Dictionary(documents.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })

        return (model?.claims ?? []).compactMap { claim -> ClaimsTableView.Item? in
            let values = ClaimTableRow(claim)
            let sourceName = Self.sourceName(for: claim.sourceDocumentId, docsById: docsById)
            guard Self.claimMatches(
                haystack: "\(values.svoLine) \(values.date) \(sourceName)",
                type: claim.claimType?.rawValue ?? "",
                search: trimmedQuery,
                filterText: filterText,
                filterType: filterType
            ) else { return nil }
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

    /// Delete the selected claims (spec: kg-tables `claim.delete`): the model deletes
    /// them server-side (one audited action each) and drops the rows in place. A
    /// failure leaves the rows and reloads from the source of truth, so the table
    /// never shows a phantom-deleted row.
    private func deleteClaims(_ claims: [Components.Schemas.KnowledgeClaim]) {
        let ids = claims.compactMap(\.id)
        guard !ids.isEmpty, let model else { return }
        Task {
            do {
                try await model.delete(claimIds: ids)
            } catch {
                await model.load(folderId: folderId)
            }
        }
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
