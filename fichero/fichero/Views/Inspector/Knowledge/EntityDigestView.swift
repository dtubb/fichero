import FicheroAPIClient
import SwiftUI

/// A researcher-focused view providing a clean digest of entities and their
/// provenance across the library. Unlike the OntologyBrowser, this view
/// prioritizes readability and a "published" feel over curation tools.
struct EntityDigestView: View {
    @Environment(EntityStore.self) private var entityStore
    @Environment(EntityService.self) private var entityService
    @State private var selectedEntityId: String?
    @State private var selectedEntityIds: Set<String> = []
    @State private var searchText = ""
    @State private var entities: [Components.Schemas.KnowledgeEntity] = []
    @State private var claimCounts: [String: Int] = [:]
    @State private var isLoading = false
    @State private var loadError: String?
    @State private var entitiesToDelete: [Components.Schemas.KnowledgeEntity] = []
    @State private var showingDeleteConfirmation = false

    var body: some View {
        HStack(spacing: 0) {
            // Column 1: The Entity Index
            entityIndexSidebar
                .frame(width: 300)

            Divider()

            // Column 2: The Entity Digest
            if let entityId = selectedEntityId,
               let entity = entities.first(where: { $0.id == entityId }) {
                EntityDigestContent(
                    entity: entity,
                    entityService: entityService
                )
                .frame(maxWidth: .infinity)
            } else {
                emptyState
                    .frame(maxWidth: .infinity)
            }
        }
        .task {
            await loadEntities()
        }
        .onChange(of: searchText) { _, _ in
            Task { await searchEntities() }
        }
        .alert("Delete Entities?", isPresented: $showingDeleteConfirmation) {
            Button("Cancel", role: .cancel) {
                entitiesToDelete = []
            }
            Button("Delete", role: .destructive) {
                let selection = entitiesToDelete
                if !selection.isEmpty {
                    Task { await deleteSelectedEntities(selection) }
                }
            }
        } message: {
            if entitiesToDelete.count == 1, let entity = entitiesToDelete.first {
                Text("Are you sure you want to delete \"\(entity.canonicalName)\"? This action cannot be undone.")
            } else if !entitiesToDelete.isEmpty {
                Text(
                    "Are you sure you want to delete \(entitiesToDelete.count) entities? This action cannot be undone."
                )
            }
        }
    }

    private var entityIndexSidebar: some View {
        VStack(spacing: 0) {
            // Search Header
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField("Search index...", text: $searchText)
                    .textFieldStyle(.plain)
                Spacer()
                Button(role: .destructive) {
                    promptDeleteSelectedEntities()
                } label: {
                    Image(systemName: "trash")
                }
                .buttonStyle(.borderless)
                .disabled(selectedEntityIds.isEmpty)
                .help("Delete selected entities")
                .accessibilityLabel("Delete Selected Entities")
            }
            .padding(12)
            .background(Color(.controlBackgroundColor))

            Divider()

            // Entity List
            List(selection: $selectedEntityIds) {
                // Spinner only before FIRST content — refreshes splice in place
                // (stale-while-revalidate, 2026-08-20 flash sweep).
                if isLoading && entities.isEmpty {
                    HStack {
                        Spacer()
                        ProgressView()
                        Spacer()
                    }
                    .listRowBackground(Color.clear)
                } else if let error = loadError {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .padding()
                        .listRowBackground(Color.clear)
                } else {
                    ForEach(entities, id: \.id) { entity in
                        indexRow(entity)
                            .tag(entity.id ?? "")
                    }
                }
            }
            .listStyle(.sidebar)
            .onChange(of: selectedEntityIds) { _, newValue in
                selectedEntityId = newValue.first
            }
            #if os(macOS)
            .onDeleteCommand(perform: promptDeleteSelectedEntities)
            #endif
        }
    }

    private func indexRow(_ entity: Components.Schemas.KnowledgeEntity) -> some View {
        // Shares the canonical EntityRow renderer in its `.digest`
        // presentation so the researcher index and the OntologyBrowser
        // sidebar stay on one code path (#1690).
        EntityRow(
            entity: entity,
            claimCount: claimCounts[entity.id ?? ""] ?? 0,
            style: .digest
        )
        .contentShape(Rectangle())
        .contextMenu {
            Button(role: .destructive) {
                if selectedEntityIds.contains(entity.id ?? "") {
                    promptDeleteSelectedEntities()
                } else {
                    confirmDelete([entity])
                }
            } label: {
                Label("Delete", systemImage: "trash")
            }
        }
    }

    private var emptyState: some View {
        ContentUnavailableView {
            Label("No Entity Selected", systemImage: "book.closed")
        } description: {
            Text("Browse the index to see reconstructed biographies and source annotations.")
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func loadEntities() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }

        do {
            // Use LibraryManager for the service if not provided via environment
            let service = entityService
            async let entityList = service.listEntities(limit: 500)
            async let counts = service.fetchClaimCounts()
            entities = try await entityList
            claimCounts = (try? await counts) ?? [:]
            let validIds = Set(entities.compactMap(\.id))
            selectedEntityIds = selectedEntityIds.intersection(validIds)
            selectedEntityId = selectedEntityIds.first
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func searchEntities() async {
        guard !searchText.isEmpty else {
            await loadEntities()
            return
        }
        do {
            entities = try await entityService.listEntities(query: searchText, limit: 500)
            let validIds = Set(entities.compactMap(\.id))
            selectedEntityIds = selectedEntityIds.intersection(validIds)
            selectedEntityId = selectedEntityIds.first
        } catch {
            // keep current entities
        }
    }

    private func promptDeleteSelectedEntities() {
        let selection = entities.filter { entity in
            guard let id = entity.id else { return false }
            return selectedEntityIds.contains(id)
        }
        confirmDelete(selection)
    }

    /// Prompt to delete a specific set of entities (e.g. a right-clicked row
    /// that isn't part of the current multi-selection).
    private func confirmDelete(_ entities: [Components.Schemas.KnowledgeEntity]) {
        guard !entities.isEmpty else { return }
        entitiesToDelete = entities
        showingDeleteConfirmation = true
    }

    private func deleteSelectedEntities(_ selection: [Components.Schemas.KnowledgeEntity]) async {
        let ids = selection.compactMap(\.id)
        guard !ids.isEmpty else { return }
        do {
            try await entityStore.delete(entityIds: ids)
            selectedEntityIds.subtract(ids)
            selectedEntityId = selectedEntityIds.first
            entitiesToDelete = []
            showingDeleteConfirmation = false
            await loadEntities()
        } catch {
            loadError = error.localizedDescription
        }
    }
}

/// The detailed digest for a single entity.
///
/// Split across four files (#4896: `type_body_length` 365/250, `file_length`
/// 784/400) — this file keeps stored state, `body`, `headerSection`, and the
/// shared `docName`/`sourceLabel` resolvers; `+Biography.swift`,
/// `+AppearsIn.swift`, `+Provenance.swift` hold the rest `body` composes. A
/// MOVE only, no behaviour change. `private` is file-scoped, not type-scoped,
/// so every member ANY other file reaches had to drop it — rather than track
/// that member by member, every stored/environment property here is internal
/// as one rule (ContentView's/LibraryView's own convention); `entitySearchState`
/// is the one exception, read only by `headerSection`, which stays here.
struct EntityDigestContent: View {
    let entity: Components.Schemas.KnowledgeEntity
    let entityService: EntityService

    /// The SHARED source cursor (#4393 part 2) — the same one the annotations
    /// list, the artifacts pane, the source outline and the KG web pane write
    /// to. Claims were the only inspector surface that could not get back to
    /// the page; this makes them a producer on the existing seam rather than a
    /// second addressing scheme. Internal: read from Biography/AppearsIn/Provenance.
    @Environment(ClaimSourceNavigationState.self)
    var claimSourceNavigationState: ClaimSourceNavigationState?

    /// Per-window entity-search bus (#3437) — the digest's name, like the
    /// detail panel's (#882), leads to every source that mentions the entity
    /// (Daniel, 2026-09-04: "see all sources related to a particular
    /// person"). Optional → safe no-op without a host. Only `headerSection`
    /// (this file) reads it — stays `private`.
    @Environment(EntitySearchState.self)
    private var entitySearchState: EntitySearchState?

    /// Optional on purpose: the digest renders in panes that may not carry
    /// the service (missing @Environment of a non-optional traps, #4513).
    /// Internal: read from AppearsIn.
    @Environment(DocumentService.self) var documentService: DocumentService?

    /// The observable data layer for claims (#3300). Optional for the same
    /// reason as `documentService`. The digest's statements load THROUGH this so
    /// an edit/merge/delete/curation change anywhere resyncs here without
    /// reselecting. (spec: kg-entity-inspector, kg.entity.statements.loads-via-store
    /// + resyncs-on-change — F3) Internal: read from `body` and Provenance.
    @Environment(ClaimStore.self) var claimStore: ClaimStore?

    /// Internal: read/written from `body` plus Biography/Provenance.
    @State var claims: [Components.Schemas.KnowledgeClaim] = []
    /// The DOCUMENTS this entity appears in (user, 2026-08-20: "tell me in
    /// the inspector at the bottom where I can find this person — the actual
    /// files"). Resolved from source_document_ids in ONE batched fetch.
    /// Internal: read/written from AppearsIn, read from this file's `docName`.
    @State var appearsIn: [Document] = []
    /// Internal: confined to AppearsIn (file-scoped `private` can't reach there).
    @State var selectedAppearsRowId: String?
    /// Internal: confined to Provenance.
    @State var selectedClaimRowId: String?
    /// Internal: read from `body`/Biography/AppearsIn/Provenance, written from
    /// `body` and Provenance's `loadClaims`.
    @State var isLoading = false
    /// The claim being edited from a biography sentence's "[Edit]" run (#4833).
    /// Read/written only from the Biography extension file — internal.
    @State var editingBiographyClaimId: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // 1. Header
                headerSection

                // 2. Biography (Reconstructed prose)
                biographySection

                // 3. Where this entity appears — the actual files.
                appearsInSection

                // 4. Source Annotations (Detailed provenance)
                provenanceSection
            }
            .padding(32)
        }
        .task(id: entity.id) {
            await loadClaims()
            await loadAppearsIn()
        }
        .onChange(of: claimStore?.changeToken) {
            // A claim mutation anywhere (edit/merge/delete/curation) bumped the
            // store — re-read this entity's statements without reselecting.
            // (spec: kg-entity-inspector, kg.entity.statements.resyncs-on-change — F3)
            Task { await loadClaims() }
        }
    }

    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                // Same contract as the detail panel's header (#882): the name
                // is the door to every source that mentions this entity — a
                // scoped search (people:"Name"), not a plain text match.
                Button {
                    entitySearchState?.request(
                        name: entity.canonicalName,
                        entityType: EntityKind(apiType: entity.entityType)?.searchScope
                    )
                } label: {
                    Text(entity.canonicalName)
                        .font(.title)
                        .fontWeight(.bold)
                }
                .buttonStyle(.plain)
                .help("Find every source that mentions \"\(entity.canonicalName)\"")

                if let type = entity.entityType {
                    Text(type.rawValue.capitalized)
                        .font(.caption)
                        .fontWeight(.medium)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Capsule().fill(Color.accentColor.opacity(0.1)))
                        .foregroundStyle(Color.accentColor)
                }
            }

            if let description = entity.description {
                Text(description)
                    .font(.title3)
                    .foregroundStyle(.secondary)
                    .italic()
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Human-readable name for a source document id, for the "Appears In" and
    /// "Source Annotations" sections. The window's stores come from the library
    /// that owns this digest's `entityService` (#4461), not `globalLibrary` —
    /// reaching for global was the #4306 shape: a non-global document is absent
    /// from the global store, so a source name degraded to a raw hash id.
    /// Internal, not private — called from both the AppearsIn and Provenance
    /// extension files (see type doc above).
    func docName(for docId: String) -> String {
        let storeDocs: [Document] = LibraryManager.shared
            .library(owningService: entityService)
            .map { $0.documentStore.currentDocuments
                + $0.documentStore.collections
                + $0.documentStore.sidebarDocuments }
            ?? []
        return Self.sourceLabel(for: docId, appearsIn: appearsIn, storeDocs: storeDocs)
    }

    /// Resolve a source-document id to a user-facing label, static so the rule is
    /// testable without mounting the view.
    ///
    /// Resolves against the entity's already-loaded source documents FIRST
    /// (`appearsIn`, fetched by id → real names — exactly the id set these two
    /// sections show), then whatever stores are loaded. NEVER surfaces the raw
    /// 32-char id as a label (Daniel: the entity view showed
    /// `68045f58a3ea47b2a4…` where a page name belongs); an unresolved id becomes
    /// a short, clearly-truncated placeholder instead of the full hash.
    static func sourceLabel(
        for docId: String,
        appearsIn: [Document],
        storeDocs: [Document]
    ) -> String {
        guard !docId.isEmpty else { return "Unknown source" }
        if let doc = appearsIn.first(where: { $0.id == docId })
            ?? storeDocs.first(where: { $0.id == docId }) {
            // Not `doc.name` (#4416): a page child's stored name is the engine's
            // upload temp file (`fichero_upload_…pdf`), so compose the display
            // title from the parent like every other surface.
            let pool = appearsIn + storeDocs
            let parent = doc.parentId.flatMap { parentId in pool.first(where: { $0.id == parentId }) }
            return DocumentTitle.displayName(for: doc, parent: parent)
        }
        // The source document isn't loaded anywhere — a short, honest placeholder,
        // never the raw hash.
        return "Source \(docId.prefix(8))…"
    }
}
