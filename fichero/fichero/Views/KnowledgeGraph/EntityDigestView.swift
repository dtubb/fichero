import FicheroAPIClient
import SwiftUI

/// A researcher-focused view providing a clean digest of entities and their
/// provenance across the library. Unlike the OntologyBrowser, this view
/// prioritizes readability and a "published" feel over curation tools.
struct EntityDigestView: View {
    @EnvironmentObject private var entityService: EntityServiceGenerated
    @State private var selectedEntityId: String?
    @State private var searchText = ""
    @State private var entities: [Components.Schemas.KnowledgeEntity] = []
    @State private var claimCounts: [String: Int] = [:]
    @State private var isLoading = false
    @State private var loadError: String?

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
    }

    private var entityIndexSidebar: some View {
        VStack(spacing: 0) {
            // Search Header
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField("Search index...", text: $searchText)
                    .textFieldStyle(.plain)
            }
            .padding(12)
            .background(Color(.controlBackgroundColor))

            Divider()

            // Entity List
            List(selection: $selectedEntityId) {
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
                            .tag(entity.id)
                    }
                }
            }
            .listStyle(.sidebar)
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
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "book.closed")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            Text("Select an entity to view its digest")
                .font(.headline)
            Text("Browse the index to see reconstructed biographies and source annotations.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
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
        } catch {
            // keep current entities
        }
    }
}

/// The detailed digest for a single entity.
struct EntityDigestContent: View {
    let entity: Components.Schemas.KnowledgeEntity
    let entityService: EntityServiceGenerated

    @State private var claims: [Components.Schemas.KnowledgeClaim] = []
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
                // Group claims by document
                let grouped = Dictionary(grouping: claims, by: \.sourceDocumentId)

                ForEach(Array(grouped.keys).sorted(), id: \.self) { docId in
                    provenanceItem(docId: docId, claims: grouped[docId] ?? [])
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func provenanceItem(docId: String, claims: [Components.Schemas.KnowledgeClaim]) -> some View {
        let docName = LibraryManager.shared.globalLibrary?.documentStore
            .currentDocuments.first(where: { $0.id == docId })?.name ?? docId

        return VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "doc.text")
                    .foregroundStyle(.secondary)
                Text(docName)
                    .fontWeight(.medium)
            }
            .font(.subheadline)

            VStack(alignment: .leading, spacing: 4) {
                ForEach(claims, id: \.id) { claim in
                    ClaimSummaryCard(claim: claim)
                }
            }
            .padding(.leading, 24)
        }
        .padding(.vertical, 8)
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
            return
        }
        do {
            claims = try await entityService.listClaims(entityId: entityId, limit: 500)
        } catch {
            claims = []
        }
    }
}
