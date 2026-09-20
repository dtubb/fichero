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
    /// Reports the row ids currently on screen (post-filter) so `LibraryView`'s
    /// ⌘A — the ONE owner of Select All (`LibraryMenuParityTests.
    /// selectAllHasOneOwner`) — can select what this table is actually
    /// showing, never a second handler (#4851/#4794, spec: kg-tables
    /// `kg.view.keyboard-delete`; same `onVisibleIds` shape
    /// `DatasetModeView` already reports through).
    var onVisibleIds: (([String]) -> Void)?
    /// #4856: the filter TEXT and TYPE now live in the shared bottom bar's
    /// filter slot — `LibraryView` owns the state, this view only reads and
    /// writes it, the same as `selection`.
    @Binding var filterText: String
    @Binding var filterType: String?
    /// #4856: set true by the shared footer's "+" when this content kind is
    /// active. Drives the SAME create sheet the old in-table "New Claim"
    /// button opened — only where the trigger lives has moved.
    @Binding var addRequested: Bool
    /// Reports this scope's loaded claim types UP so the shared footer's
    /// type menu (§ `filterType`) has rows to offer — only the content knows
    /// what its own loaded rows contain.
    var onAvailableTypesChanged: (([String]) -> Void)?

    /// The SHARED source cursor — a claim row opens its page + highlight through
    /// the same seam the claim card and entity biography use. Optional → safe
    /// no-op without a host.
    @Environment(ClaimSourceNavigationState.self) private var cursor: ClaimSourceNavigationState?

    /// #4886 master/detail: the per-window "an entity is focused" signal — the
    /// SAME one an Entities pane's row click already sets
    /// (`LibraryView+Selection.swift`'s `openEntityFromLibrary`), no new wiring.
    @Environment(KGFocusState.self) private var kgFocusState: KGFocusState?
    /// #4886: when an entity is focused, this pane reads/acts THROUGH the
    /// EXISTING per-library `ClaimStore.loadClaims(forEntity:)`/`.delete` —
    /// never a second loader (the maintainer's standing objection to duplicate
    /// code paths). Safe today: traced every reader of `claimStore.claims` —
    /// the ONLY live consumer is the entity digest's `.entity` scope
    /// (`EntityDigestContent+Provenance.swift`), which is always the SAME
    /// entity `kgFocusState` names, so sharing the store's one scope is "one
    /// fetch, two renderers," not a fight. `ClaimStore.loadClaims(forDocument:)`
    /// has ZERO production callers today — the document Inspector's Knowledge
    /// tab uses a separate endpoint (`documentKnowledgeGraph`) and its own
    /// local state, not this store — so there is no `.document`-scope reader
    /// to collide with. KNOWN CAVEAT (#4913, pre-existing, not introduced
    /// here): `ClaimStore` is per-LIBRARY but `kgFocusState` is per-WINDOW, so
    /// two windows on the same library focused on different entities race the
    /// same shared scope — already true for two Inspectors today.
    @Environment(ClaimStore.self) private var claimStore: ClaimStore?
    /// Pane-local dismissal of the entity narrowing ("Show All") — deliberately
    /// NOT `kgFocusState.focusedEntityId = nil`, which would blank the
    /// Inspector's biography if it's following the same focus. Resets to
    /// `false` the moment the WINDOW's focus moves to a genuinely different
    /// entity (`showingAllResets(from:to:)` below) — "Show All" dismisses
    /// THIS narrowing, it doesn't opt the pane out of master/detail forever.
    @State private var showingAllOverride = false

    @State private var model: LibraryClaimsModel?

    /// The library the cached `model` was built for. `EntityService` is per-library
    /// and captured permanently by `LibraryClaimsModel.init`, so a library switch
    /// must rebuild the model — otherwise the table keeps loading the PREVIOUS
    /// library's claims (spec: panes-workspaces F5). `nil` until first
    /// build. See `.task(id:)` below. The active library id comes from the existing
    /// `windowState` (declared below) — a library-wide Claims row keeps
    /// `folderId == nil` before AND after a switch, so keying the reload on
    /// `folderId` alone never refired across libraries (the F5 bug).
    @State private var loadedLibraryId: UUID?

    /// The claim being edited (spec: kg-tables `claim.edit`). Presents the EXISTING
    /// `EditClaimSheet` (PATCH). A tiny Identifiable wrapper is needed because
    /// `KnowledgeClaim.id` is optional, which `.sheet(item:)` cannot key on.
    @State private var claimToEdit: Components.Schemas.KnowledgeClaim?

    /// This view's own library/folder-switch reload keying (below), not
    /// `EditClaimSheet`'s — #4833 moved that sheet's save off
    /// `LibraryManager.shared.getLibrary(id:)` onto the per-window
    /// `ClaimStore`, so it no longer reads `WindowState` at all.
    @Environment(WindowState.self) private var windowState

    /// Resolves a claim's source document id → its real name even when that
    /// document isn't in the folder-scoped `documents` (the library-wide claims
    /// table shows claims whose source lives anywhere in the library). Without
    /// this the Source column fell back to a raw "Source 2a614b56…" id (spec:
    /// panes-workspaces panes.claim.source-is-document).
    @Environment(DocumentStore.self) private var documentStore
    /// Resolves the focused entity's display name for the "Claims about <name>"
    /// header (#4886). Already in the same window-environment list as
    /// `kgFocusState`/`claimStore` — no new plumbing.
    @Environment(EntityStore.self) private var entityStore: EntityStore?

    private struct EditingClaim: Identifiable {
        let claim: Components.Schemas.KnowledgeClaim
        var id: String { claim.id ?? claim.text }
    }

    var body: some View {
        VStack(spacing: 0) {
            // #4886: narrowed-scope header — silent filtering reads as a bug.
            if case .entity = scope {
                narrowedHeader
            }
            // #4856: no second bar here any more — the filter and the add
            // control both moved into the shared bottom bar's slots
            // (`LibraryView+BottomActionBar.swift`), so a table pane spends
            // exactly one bar's height, not two.
            ClaimsTableView(
                items: items,
                selection: $selection,
                isLoading: isLoading,
                emptyMessage: emptyMessage,
                onOpenSource: openSource,
                onDelete: deleteClaims,
                onEdit: { claimToEdit = $0 },
                onRevealSource: revealSource
            )
        }
        // Reload on BOTH the active library AND the folder scope. Keying on
        // `folderId` alone left the library-wide row (folderId == nil) stuck on
        // the previous library's claims after a switch (spec F5). The cached
        // model captured the OLD library's per-library `EntityService`, so a
        // switch also REBUILDS it — a stale-service model must not survive.
        // Kept running even while entity-scoped (#4886): the folder data stays
        // warm in the background, so "Show All" never shows an avoidable spinner.
        .task(id: LibraryClaimsModel.reloadKey(libraryId: windowState.libraryId, folderId: folderId)) {
            if model == nil || loadedLibraryId != windowState.libraryId {
                model = LibraryClaimsModel(service: entityService)
                loadedLibraryId = windowState.libraryId
            }
            await model?.load(folderId: folderId)
        }
        // #4886: the entity-scoped load, through the EXISTING ClaimStore seam
        // (see the doc comment on `claimStore` above for why sharing it is
        // safe today, and #4913 for the pre-existing cross-window caveat).
        // Keyed on the focused entity id alone, independent of `showingAllOverride`
        // — the store stays warm whether or not THIS pane is currently showing it.
        .task(id: kgFocusState?.focusedEntityId) {
            guard let entityId = kgFocusState?.focusedEntityId else { return }
            await claimStore?.loadClaims(forEntity: entityId)
        }
        // #4886: "Show All" dismisses THIS narrowing only; a genuinely NEW
        // focus re-engages master/detail (the pure `showingAllResets` rule).
        .onChange(of: kgFocusState?.focusedEntityId) { old, new in
            if Self.showingAllResets(from: old, to: new) {
                showingAllOverride = false
            }
        }
        .sheet(isPresented: $addRequested) {
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
            // Reuse the existing SVO editor (PATCH, #4833: now via ClaimStore).
            // On save, reload whichever scope is ACTIVE so the row reflects the
            // edit (#4886: reloading only the folder path would leave an
            // entity-narrowed table showing the stale pre-edit row).
            EditClaimSheet(claim: wrapped.claim) { _ in
                claimToEdit = nil
                Task { await reloadActiveScope() }
            }
        }
        // #4851/#4794: report the visible ids on every input that can change
        // them — the filter inputs directly, and either scope's own load
        // finishing (covers the initial load, a folder/library switch, AND an
        // entity focus/unfocus, #4886). Mirrors `DatasetModeView.reportVisible()`'s
        // trigger set. `items` itself already re-derives from whichever store
        // (`model` or `claimStore`) is active, so this needs no OTHER new wiring
        // — Select All keeps seeing exactly the narrowed list this pane shows.
        // #4856 folds in reporting the scope's available TYPES on the same
        // triggers — the shared footer's type menu (§ `filterType`) needs
        // them the moment this content becomes the active one, same as the
        // visible ids.
        .onChange(of: items.map(\.id)) { _, newIds in
            onVisibleIds?(newIds)
            onAvailableTypesChanged?(availableTypes)
        }
        .onChange(of: filterText) { _, _ in onVisibleIds?(items.map(\.id)) }
        .onChange(of: filterType) { _, _ in onVisibleIds?(items.map(\.id)) }
        .onChange(of: searchQuery) { _, _ in onVisibleIds?(items.map(\.id)) }
        .onChange(of: model?.isLoading) { _, loading in
            if loading == false {
                onVisibleIds?(items.map(\.id))
                onAvailableTypesChanged?(availableTypes)
            }
        }
        .onChange(of: claimStore?.isLoading) { _, loading in
            if loading == false {
                onVisibleIds?(items.map(\.id))
                onAvailableTypesChanged?(availableTypes)
            }
        }
    }

    /// #4886: which claims this pane is scoped to right now — an explicit
    /// entity focus wins over the folder, UNLESS the user dismissed it with
    /// "Show All" for this pane. Pure, testable off-view.
    enum ClaimsScope: Equatable {
        case folder(String?)
        case entity(String)
    }

    // `ClaimsLibraryContent` is a View, so its statics are @MainActor by
    // default (#4902-class trap) — `nonisolated` is load-bearing for a
    // non-@MainActor Swift Testing suite to call these directly. Both are
    // pure over their parameters.
    nonisolated static func effectiveScope(
        focusedEntityId: String?,
        folderId: String?,
        showingAllOverride: Bool
    ) -> ClaimsScope {
        if !showingAllOverride, let focusedEntityId {
            return .entity(focusedEntityId)
        }
        return .folder(folderId)
    }

    /// Whether the WINDOW's focus moved to a genuinely different entity (or
    /// cleared) — the rule that resets "Show All" so it dismisses one
    /// narrowing rather than opting the pane out of master/detail forever.
    nonisolated static func showingAllResets(from old: String?, to new: String?) -> Bool {
        old != new
    }

    private var scope: ClaimsScope {
        Self.effectiveScope(
            focusedEntityId: kgFocusState?.focusedEntityId,
            folderId: folderId,
            showingAllOverride: showingAllOverride
        )
    }

    private var isLoading: Bool {
        switch scope {
        case .folder: return model?.isLoading ?? true
        case .entity: return claimStore?.isLoading ?? true
        }
    }

    /// Re-fetch whichever scope is currently active (used after an edit).
    private func reloadActiveScope() async {
        switch scope {
        case .folder:
            await model?.load(folderId: folderId)
        case .entity(let entityId):
            await claimStore?.loadClaims(forEntity: entityId, force: true)
        }
    }

    /// The focused entity's display name for the header, resolved from the
    /// SAME per-library `EntityStore` every other KG surface reads — never a
    /// raw id. A graceful placeholder while the entity itself hasn't loaded.
    private var focusedEntityName: String {
        guard let id = kgFocusState?.focusedEntityId else { return "" }
        return entityStore?.libraryEntities.first(where: { $0.id == id })?.canonicalName
            ?? "this entity"
    }

    @ViewBuilder
    private var narrowedHeader: some View {
        HStack {
            Text("Claims about \(focusedEntityName)")
                .font(.headline)
            Spacer()
            Button("Show All") { showingAllOverride = true }
                .font(.subheadline)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
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

    /// The claims backing THIS pane right now — `model`'s folder-scoped list,
    /// or `claimStore`'s entity-scoped one (#4886), whichever `scope` picked.
    private var scopedClaims: [Components.Schemas.KnowledgeClaim] {
        switch scope {
        case .folder: return model?.claims ?? []
        case .entity: return claimStore?.claims ?? []
        }
    }

    /// The claim types present in the loaded set, for the type picker.
    private var availableTypes: [String] {
        Array(Set(scopedClaims.compactMap { $0.claimType?.rawValue })).sorted()
    }

    private var emptyMessage: String {
        let loadError: String? = {
            switch scope {
            case .folder: return model?.loadError
            case .entity: return claimStore?.loadError
            }
        }()
        if let error = loadError {
            return "Couldn't load claims: \(error)"
        }
        if let query = trimmedQuery, filterText.isEmpty, filterType == nil {
            return "No claims match “\(query)”."
        }
        if trimmedQuery != nil || !filterText.isEmpty || filterType != nil {
            return "No claims match the current filter."
        }
        // #4886: the narrowed-scope empty state names what it's scoped to —
        // "No claims in this folder" would be actively misleading here.
        if case .entity = scope {
            return "No claims about \(focusedEntityName) yet."
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

        return scopedClaims.compactMap { claim -> ClaimsTableView.Item? in
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
        // #4834: this fires from the row's OWN selection changing
        // (`.onChange(of: selection)` in ClaimsTableView) — "a table row
        // click IS a selection," left unchanged; `.reader` stated explicitly.
        guard let request = ClaimSourceRequest.request(for: claim, destination: .reader) else { return }
        cursor?.request(request)
    }

    /// #4834 slice E: the context-menu "Reveal Source" item — the smallest
    /// addition that shows a claim's evidence WITHOUT touching the row
    /// selection (`.both`), for when the user wants to see the source but
    /// not navigate away from whatever else they've selected.
    private func revealSource(_ claim: Components.Schemas.KnowledgeClaim) {
        guard let request = ClaimSourceRequest.request(for: claim, destination: .both) else { return }
        cursor?.request(request)
    }

    /// Delete the selected claims (spec: kg-tables `claim.delete`): the model deletes
    /// them server-side (one audited action each) and drops the rows in place. A
    /// failure leaves the rows and reloads from the source of truth, so the table
    /// never shows a phantom-deleted row.
    private func deleteClaims(_ claims: [Components.Schemas.KnowledgeClaim]) {
        let ids = claims.compactMap(\.id)
        guard !ids.isEmpty else { return }
        // #4886: through whichever store is BACKING the visible rows — both
        // `ClaimStore.delete` and `LibraryClaimsModel.delete` splice the row
        // out of their own array in place (no wholesale reload) on success.
        switch scope {
        case .folder:
            guard let model else { return }
            Task {
                do {
                    try await model.delete(claimIds: ids)
                } catch {
                    await model.load(folderId: folderId)
                }
            }
        case .entity:
            guard let claimStore else { return }
            Task {
                do {
                    try await claimStore.delete(claimIds: ids)
                } catch {
                    await reloadActiveScope()
                }
            }
        }
    }

    /// Every document that can resolve a claim's source name: the store's whole
    /// loaded set (so a library-wide claim's source resolves even outside the
    /// browsed folder) with the folder-scoped `documents` overlaid so the
    /// freshest copy of a visible row wins. This is what fixes the raw-id Source
    /// column (spec: panes-workspaces panes.claim.source-is-document).
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
