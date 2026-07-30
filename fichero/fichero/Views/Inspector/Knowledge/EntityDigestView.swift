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
                Text("Are you sure you want to delete \(entitiesToDelete.count) entities? This action cannot be undone.")
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
            }
            .padding(12)
            .background(Color(.controlBackgroundColor))

            Divider()

            // Entity List
            List(selection: $selectedEntityIds) {
                if isLoading {
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
struct EntityDigestContent: View {
    let entity: Components.Schemas.KnowledgeEntity
    let entityService: EntityService

    @State private var claims: [Components.Schemas.KnowledgeClaim] = []
    @State private var selectedClaimRowId: String?
    @State private var isLoading = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // 1. Header
                headerSection

                // 2. Biography (Reconstructed prose)
                biographySection

                // 3. Source Annotations (Detailed provenance)
                provenanceSection
            }
            .padding(32)
        }
        .task(id: entity.id) {
            await loadClaims()
        }
    }

    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Text(entity.canonicalName)
                    .font(.system(size: 32, weight: .bold, design: .serif))

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

    private var biographySection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Biography")
                .font(.headline)
                .padding(.bottom, 4)

            if isLoading {
                ProgressView()
            } else if claims.isEmpty {
                Text("No claims available to reconstruct a biography.")
                    .foregroundStyle(.secondary)
                    .italic()
            } else {
                Text(composedBiography)
                    .font(.body)
                    .lineSpacing(6)
                    .textSelection(.enabled)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var provenanceSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Source Annotations")
                .font(.headline)
                .padding(.bottom, 4)

            if isLoading {
                ProgressView()
            } else if claims.isEmpty {
                Text("No source citations available.")
                    .foregroundStyle(.secondary)
            } else {
                let grouped = Dictionary(grouping: claims, by: { $0.sourceDocumentId ?? "" })
                let sortedDocIds = grouped.keys.sorted()

                // Single-selection List with STABLE, non-optional tags. The old
                // `.tag(claim.id)` was `String?` while the selection was
                // `Set<String>` — the type mismatch collapsed identity so
                // clicking one row highlighted them all. A `String?` selection
                // matched by non-optional `String` tags fixes it, and
                // `inspectorListRowTarget()` makes the whole row the hit target.
                List(selection: $selectedClaimRowId) {
                    ForEach(sortedDocIds, id: \.self) { docId in
                        Section(header: Label(docName(for: docId), systemImage: "doc.text")) {
                            ForEach(Array((grouped[docId] ?? []).enumerated()), id: \.offset) { index, claim in
                                provenanceRow(claim)
                                    .inspectorListRowTarget()
                                    .tag(claim.id ?? "\(docId)#\(index)")
                                    .listRowSeparator(.hidden)
                            }
                        }
                    }
                }
                .listStyle(.inset)
                .scrollContentBackground(.hidden)
                .frame(minHeight: 160, maxHeight: 520)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func provenanceRow(_ claim: Components.Schemas.KnowledgeClaim) -> some View {
        let summary = provenanceSummary(for: claim)
        let badge = provenanceBadgeLabel(for: claim)

        return HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text(summary)
                .font(.body)
                .textSelection(.enabled)
                .lineLimit(2)

            Spacer(minLength: 8)

            Text(badge)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .padding(.vertical, 2)
    }

    /// Human-readable name for a source document id. Searches every store the
    /// app has loaded — current page/folder, collections, and the sidebar — not
    /// just `currentDocuments`, so an off-page source resolves to its title
    /// instead of a raw hash. Falls back to the id only when the document isn't
    /// in any store (that residual case needs a title on the claim payload).
    private func docName(for docId: String) -> String {
        guard let store = LibraryManager.shared.globalLibrary?.documentStore else { return docId }
        let all = store.currentDocuments + store.collections + store.sidebarDocuments
        return all.first(where: { $0.id == docId })?.name ?? docId
    }

    /// The entity this digest is showing, which every claim below is grouped
    /// under — so its name is redundant on each row (#4393).
    ///
    /// Read from `entity`, this view's own input. The first attempt reached for
    /// `selectedEntityId` / `entities`, which are `@State` on
    /// `EntityDigestView` — a DIFFERENT type in the same file. One file, two
    /// views, and the properties looked ambient because they were a few
    /// hundred lines up.
    private var groupSubject: String? { entity.canonicalName }

    private func provenanceSummary(for claim: Components.Schemas.KnowledgeClaim) -> String {
        let svo = ClaimSummaryCard.svoTriple(for: claim)
        return ClaimLine.text(
            subject: svo?.subject,
            verb: svo?.verb,
            object: svo?.object,
            fallback: claim.text,
            groupSubject: groupSubject
        )
    }

    private func provenanceBadgeLabel(for claim: Components.Schemas.KnowledgeClaim) -> String {
        let metadata = claim.metadata?.additionalProperties.value ?? [:]
        let raw = (
            claim.confidenceSource
            ?? metadata["confidence_source"] as? String
            ?? metadata["confidenceSource"] as? String
        )?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()

        switch raw {
        case "human_review", "human", "manual", "user", "curator", "editor", "researcher":
            return "Human"
        case "llm_logprob", "llm", "ai", "agent":
            return "Llm"
        case "heuristic", "default", "corroboration":
            return "Heuristic"
        case let value? where !value.isEmpty:
            return value.replacingOccurrences(of: "_", with: " ").capitalized
        default:
            return "Heuristic"
        }
    }

    private var composedBiography: String {
        var first = true
        var sentences: [String] = []

        for claim in claims {
            // Basic SVO extraction
            let subject = first ? entity.canonicalName : "they"
            first = false

            let verb = claim.predicateVerb ?? ""
            let object = claim.objectPhrase ?? ""

            if verb.isEmpty && object.isEmpty { continue }

            let docName = LibraryManager.shared.globalLibrary?.documentStore.currentDocuments.first(
                where: { $0.id == claim.sourceDocumentId }
            )?.name
            let citation = docName.map { " [\($0)]" } ?? ""
            let sentence = "\(subject) \(verb) \(object)\(citation)."
            sentences.append(sentence)
        }

        return sentences.isEmpty ? "No biography data available." : sentences.joined(separator: " ")
    }

    private func loadClaims() async {
        isLoading = true
        defer { isLoading = false }
        guard let entityId = entity.id else {
            claims = []
            selectedClaimRowId = nil
            return
        }
        do {
            claims = try await entityService.listClaims(entityId: entityId, limit: 500)
            selectedClaimRowId = nil
        } catch {
            claims = []
            selectedClaimRowId = nil
        }
    }
}
