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

    /// The library the cached `model` was built for. `EntityService` is per-library
    /// and captured permanently by `LibraryClaimsModel.init`, so a library switch
    /// must rebuild the model — otherwise the table keeps loading the PREVIOUS
    /// library's claims (spec: panes-magnifiers-workspaces F5). `nil` until first
    /// build. See `.task(id:)` below. The active library id comes from the existing
    /// `windowState` (declared below) — a library-wide Claims row keeps
    /// `folderId == nil` before AND after a switch, so keying the reload on
    /// `folderId` alone never refired across libraries (the F5 bug).
    @State private var loadedLibraryId: UUID?

    /// Per-table filter (spec: kg-tables, filter.text / filter.claim-type). Intersects
    /// with the shared ⌘F `searchQuery`; empty text + nil type = no per-table filter.
    @State private var filterText = ""
    @State private var filterType: String?

    /// Presents the manual claim-create sheet (spec: kg-tables `claim.create`).
    @State private var showingCreateSheet = false

    /// The claim being edited (spec: kg-tables `claim.edit`). Presents the EXISTING
    /// `EditClaimSheet` (PATCH). A tiny Identifiable wrapper is needed because
    /// `KnowledgeClaim.id` is optional, which `.sheet(item:)` cannot key on.
    @State private var claimToEdit: Components.Schemas.KnowledgeClaim?

    /// EditClaimSheet reads WindowState non-optionally; a `.sheet` is a hosting
    /// boundary, so this is grabbed here and re-injected across it.
    @Environment(WindowState.self) private var windowState

    /// Resolves a claim's source document id → its real name even when that
    /// document isn't in the folder-scoped `documents` (the library-wide claims
    /// table shows claims whose source lives anywhere in the library). Without
    /// this the Source column fell back to a raw "Source 2a614b56…" id (spec:
    /// panes-magnifiers-workspaces panes.claim.source-is-document).
    @Environment(DocumentStore.self) private var documentStore

    private struct EditingClaim: Identifiable {
        let claim: Components.Schemas.KnowledgeClaim
        var id: String { claim.id ?? claim.text }
    }

    var body: some View {
        VStack(spacing: 0) {
            filterBar
            ClaimsTableView(
                items: items,
                selection: $selection,
                isLoading: model?.isLoading ?? true,
                emptyMessage: emptyMessage,
                onOpenSource: openSource,
                onDelete: deleteClaims,
                onEdit: { claimToEdit = $0 }
            )
        }
        // Reload on BOTH the active library AND the folder scope. Keying on
        // `folderId` alone left the library-wide row (folderId == nil) stuck on
        // the previous library's claims after a switch (spec F5). The cached
        // model captured the OLD library's per-library `EntityService`, so a
        // switch also REBUILDS it — a stale-service model must not survive.
        .task(id: LibraryClaimsModel.reloadKey(libraryId: windowState.libraryId, folderId: folderId)) {
            if model == nil || loadedLibraryId != windowState.libraryId {
                model = LibraryClaimsModel(service: entityService)
                loadedLibraryId = windowState.libraryId
            }
            await model?.load(folderId: folderId)
        }
        .sheet(isPresented: $showingCreateSheet) {
            // Attribute the hand-authored claim to the folder/page in view so it
            // appears in this scope after reload; a nil folder makes a sourceless
            // working hypothesis (library-wide "Claims").
            NewClaimSheet(
                entityService: entityService,
                sourceDocumentId: folderId,
                onCreated: handleCreatedClaim
            )
        }
        .sheet(item: Binding(
            get: { claimToEdit.map(EditingClaim.init) },
            set: { claimToEdit = $0?.claim }
        )) { wrapped in
            // Reuse the existing SVO editor (PATCH). Re-inject WindowState across the
            // sheet boundary. On save, reload the scope so the row reflects the edit.
            EditClaimSheet(claim: wrapped.claim) { _ in
                claimToEdit = nil
                Task { await model?.load(folderId: folderId) }
            }
            .environment(windowState)
        }
    }

    /// After a manual create, reload the folder scope so the new claim appears, and
    /// select it. LibraryClaimsModel is not a change consumer, so the reload is
    /// explicit (the source of truth), never an optimistic insert.
    private func handleCreatedClaim(_ claim: Components.Schemas.KnowledgeClaim) {
        guard let model else { return }
        Task {
            await model.load(folderId: folderId)
            let docsById = self.docsById
            let parent = docsById[claim.sourceDocumentId ?? ""]
                ?? Document(id: claim.sourceDocumentId ?? "unknown",
                            name: Self.sourceName(for: claim, docsById: docsById))
            selection = [LibraryOutlineNode.claimItem(claim, parent: parent).id]
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
            // Manual create (spec: kg-tables `claim.create`) — hand-author a claim
            // from the table, wiring POST /api/claims via EntityService.createClaim.
            Button {
                showingCreateSheet = true
            } label: {
                Label("New Claim", systemImage: "plus")
            }
            .help("Assert a claim by hand")
            .accessibilityIdentifier("kg.claim.new")
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
        let docsById = self.docsById

        return (model?.claims ?? []).compactMap { claim -> ClaimsTableView.Item? in
            let values = ClaimTableRow(claim)
            let sourceName = Self.sourceName(for: claim, docsById: docsById)
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
            let sourceDoc = docsById[claim.sourceDocumentId ?? ""]
            let parent = sourceDoc
                ?? Document(id: claim.sourceDocumentId ?? "unknown", name: sourceName)
            // The Source cell drags the source DOCUMENT with the SAME payload a
            // library row uses (spec: panes.claim.source-is-document) — only when
            // the document actually resolves; an unresolved id has nothing honest
            // to drag.
            let sourceDrag = sourceDoc.map { LibraryItemDrag.forDocument($0, libraryId: windowState.libraryId) }
            return ClaimsTableView.Item(
                node: LibraryOutlineNode.claimItem(claim, parent: parent),
                claim: claim,
                values: values,
                sourceName: sourceName,
                sourceDrag: sourceDrag
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

    /// Every document that can resolve a claim's source name: the store's whole
    /// loaded set (so a library-wide claim's source resolves even outside the
    /// browsed folder) with the folder-scoped `documents` overlaid so the
    /// freshest copy of a visible row wins. This is what fixes the raw-id Source
    /// column (spec: panes-magnifiers-workspaces panes.claim.source-is-document).
    private var docsById: [String: Document] {
        var map = documentStore.knownDocumentsById()
        for doc in documents { map[doc.id] = doc }
        return map
    }

    /// The display name of a resolved source document (with its parent for
    /// disambiguation), or nil when the id isn't loaded — the resolver the pure
    /// `LibraryClaimsModel.sourceLabel` calls.
    static func resolvedName(for docId: String, docsById: [String: Document]) -> String? {
        guard let doc = docsById[docId] else { return nil }
        let parent = doc.parentId.flatMap { docsById[$0] }
        return DocumentTitle.displayName(for: doc, parent: parent)
    }

    /// Human name for a claim's source document — its page title when the document
    /// is loaded, else a short, non-raw placeholder (never the 32-char id, never
    /// empty). Delegates the rule to the pure, unit-tested
    /// `LibraryClaimsModel.sourceLabel`.
    static func sourceName(
        for claim: Components.Schemas.KnowledgeClaim,
        docsById: [String: Document]
    ) -> String {
        LibraryClaimsModel.sourceLabel(for: claim) { resolvedName(for: $0, docsById: docsById) }
    }
}
