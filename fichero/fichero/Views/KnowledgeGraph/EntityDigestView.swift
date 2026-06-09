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
    @State private var selectedClaimIds: Set<String> = []
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
                let grouped = Dictionary(grouping: claims, by: \.sourceDocumentId)
                let sortedDocIds = grouped.keys.sorted()

                List(selection: $selectedClaimIds) {
                    ForEach(sortedDocIds, id: \.self) { docId in
                        Section(header: Label(docName(for: docId), systemImage: "doc.text")) {
                            ForEach(grouped[docId] ?? [], id: \.id) { claim in
                                provenanceRow(claim)
                                    .tag(claim.id)
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

    private func docName(for docId: String) -> String {
        LibraryManager.shared.globalLibrary?.documentStore
            .currentDocuments.first(where: { $0.id == docId })?.name ?? docId
    }

    private func provenanceSummary(for claim: Components.Schemas.KnowledgeClaim) -> String {
        if let svo = ClaimSummaryCard.svoTriple(for: claim) {
            return [svo.subject, svo.verb, svo.object]
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
                .joined(separator: " · ")
        }

        let fallback = claim.text.trimmingCharacters(in: .whitespacesAndNewlines)
        return fallback.isEmpty ? "Untitled claim" : fallback
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
            selectedClaimIds.removeAll()
            return
        }
        do {
            claims = try await entityService.listClaims(entityId: entityId, limit: 500)
            selectedClaimIds.removeAll()
        } catch {
            claims = []
            selectedClaimIds.removeAll()
        }
    }
}
