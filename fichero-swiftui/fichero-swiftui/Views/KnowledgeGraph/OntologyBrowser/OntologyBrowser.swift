import SwiftUI
import FicheroAPIClient

/// Browser panel for exploring entities and their associated claims
struct OntologyBrowser: View {
    @State private var selectedEntityId: String?
    @State private var searchText = ""
    @State private var isSearching = false

    var body: some View {
        HSplitView {
            entityListSidebar
            entityDetailPanel
        }
        .frame(minWidth: 300, minHeight: 200)
    }

    // MARK: - Entity List Sidebar

    private var entityListSidebar: some View {
        VStack(spacing: 0) {
            searchBar
            Divider()
            entityList
        }
        .frame(minWidth: 200, maxWidth: 300)
    }

    private var searchBar: some View {
        HStack {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.secondary)

            TextField("Search entities...", text: $searchText)
                .textFieldStyle(.plain)
                .onSubmit {
                    Task { await searchEntities() }
                }

            if isSearching {
                ProgressView()
                    .scaleEffect(0.7)
            }
        }
        .padding(8)
        .background(Color(.controlBackgroundColor))
    }

    @State private var entities: [Components.Schemas.EntityCoreference] = []
    @State private var loadError: String?
    @State private var isLoading = false

    private var entityList: some View {
        List(selection: $selectedEntityId) {
            if isLoading {
                HStack {
                    Spacer()
                    ProgressView()
                    Spacer()
                }
                .listRowBackground(Color.clear)
            } else if let error = loadError {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundStyle(.orange)
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding()
                .listRowBackground(Color.clear)
            } else if entities.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "person.2")
                        .font(.system(size: 28))
                        .foregroundStyle(.secondary)
                    Text("No Entities")
                        .font(.subheadline)
                    Text("Entities will appear as you create claims")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding()
                .listRowBackground(Color.clear)
            } else {
                ForEach(entities, id: \.entityId) { entity in
                    EntityRow(entity: entity)
                        .tag(entity.entityId)
                }
            }
        }
        .listStyle(.sidebar)
        .task {
            await loadEntities()
        }
    }

    private func loadEntities() async {
        isLoading = true
        loadError = nil

        do {
            let library = LibraryManager.shared.globalLibrary
            let service = KnowledgeGraphServiceGenerated(apiClient: library!.apiClient)
            entities = try await service.listEntities(limit: 100)
        } catch {
            loadError = error.localizedDescription
        }

        isLoading = false
    }

    private func searchEntities() async {
        guard !searchText.isEmpty else {
            await loadEntities()
            return
        }

        isLoading = true
        loadError = nil

        do {
            let library = LibraryManager.shared.globalLibrary
            let service = KnowledgeGraphServiceGenerated(apiClient: library!.apiClient)
            let resolved = try await service.resolveEntity(value: searchText)
            entities = [resolved]
        } catch {
            // Fall back to listing all entities
            await loadEntities()
        }

        isLoading = false
    }

    // MARK: - Entity Detail Panel

    @State private var entityClaims: [Components.Schemas.KnowledgeClaim] = []
    @State private var isLoadingClaims = false

    private var entityDetailPanel: some View {
        Group {
            if let entityId = selectedEntityId,
               let entity = entities.first(where: { $0.entityId == entityId }) {
                EntityDetailView(
                    entity: entity,
                    claims: entityClaims,
                    isLoadingClaims: isLoadingClaims
                )
                .task {
                    await loadEntityClaims(entityId: entityId)
                }
            } else {
                emptyDetailState
            }
        }
        .frame(minWidth: 250)
    }

    private var emptyDetailState: some View {
        VStack(spacing: 12) {
            Image(systemName: "person.crop.rectangle.stack")
                .font(.system(size: 36))
                .foregroundColor(.secondary)

            Text("No Entity Selected")
                .font(.headline)

            Text("Select an entity to view its details")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    private func loadEntityClaims(entityId: String) async {
        isLoadingClaims = true

        do {
            let library = LibraryManager.shared.globalLibrary
            let service = KnowledgeGraphServiceGenerated(apiClient: library!.apiClient)
            entityClaims = try await service.filterClaims(entityIds: [entityId], limit: 50)
        } catch {
            entityClaims = []
        }

        isLoadingClaims = false
    }
}

// MARK: - Entity Row

private struct EntityRow: View {
    let entity: Components.Schemas.EntityCoreference

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: iconForEntityType)
                .foregroundStyle(.secondary)
                .frame(width: 16)

            VStack(alignment: .leading, spacing: 2) {
                Text(entity.canonicalName)
                    .font(.subheadline)
                    .lineLimit(1)

                if let aliases = entity.aliases, !aliases.isEmpty {
                    Text(aliases.prefix(2).joined(separator: ", "))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
        }
        .padding(.vertical, 4)
    }

    private var iconForEntityType: String {
        guard let type = entity.entityType else { return "person.fill" }
        switch type {
        case .person: return "person.fill"
        case .organization: return "building.2.fill"
        case .location: return "mappin.circle.fill"
        case .event: return "calendar.circle.fill"
        case .document: return "doc.fill"
        case .concept: return "lightbulb.fill"
        case .other: return "circle.fill"
        }
    }
}

// MARK: - Entity Detail View

private struct EntityDetailView: View {
    let entity: Components.Schemas.EntityCoreference
    let claims: [Components.Schemas.KnowledgeClaim]
    let isLoadingClaims: Bool

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                headerSection
                aliasesSection
                claimsSection
            }
            .padding()
        }
    }

    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: iconForEntityType)
                    .font(.system(size: 24))
                    .foregroundStyle(.accentColor)

                Text(entity.canonicalName)
                    .font(.title2)
                    .fontWeight(.semibold)
            }

            if let description = entity.description {
                Text(description)
                    .font(.body)
                    .foregroundStyle(.secondary)
            }

            if let entityType = entity.entityType {
                LabeledContent("Type") {
                    Text(entityType.rawValue.capitalized)
                        .foregroundStyle(.secondary)
                }
            }

            if let language = entity.language {
                LabeledContent("Language") {
                    Text(language.uppercased())
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private var iconForEntityType: String {
        guard let type = entity.entityType else { return "person.fill" }
        switch type {
        case .person: return "person.fill"
        case .organization: return "building.2.fill"
        case .location: return "mappin.circle.fill"
        case .event: return "calendar.circle.fill"
        case .document: return "doc.fill"
        case .concept: return "lightbulb.fill"
        case .other: return "circle.fill"
        }
    }

    private var aliasesSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Aliases")
                .font(.subheadline)
                .fontWeight(.semibold)

            if let aliases = entity.aliases, !aliases.isEmpty {
                FlowLayout(spacing: 6) {
                    ForEach(aliases, id: \.self) { alias in
                        Text(alias)
                            .font(.caption)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.accentColor.opacity(0.1))
                            .clipShape(RoundedRectangle(cornerRadius: 4))
                    }
                }
            } else {
                Text("No aliases")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private var claimsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Claims")
                    .font(.subheadline)
                    .fontWeight(.semibold)

                Spacer()

                if isLoadingClaims {
                    ProgressView()
                        .scaleEffect(0.7)
                } else {
                    Text("\(claims.count)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if isLoadingClaims {
                HStack {
                    Spacer()
                    ProgressView()
                    Spacer()
                }
                .padding(.vertical, 20)
            } else if claims.isEmpty {
                Text("No claims reference this entity")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 12)
            } else {
                ForEach(claims.prefix(10), id: \.id) { claim in
                    ClaimSummaryCard(claim: claim)
                }

                if claims.count > 10 {
                    Text("+ \(claims.count - 10) more claims")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .padding(.top, 4)
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

// MARK: - Claim Summary Card

private struct ClaimSummaryCard: View {
    let claim: Components.Schemas.KnowledgeClaim

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(claim.text)
                .font(.caption)
                .lineLimit(2)
                .textSelection(.enabled)

            HStack(spacing: 8) {
                if let claimType = claim.claimType {
                    Text(claimType.rawValue.capitalized)
                        .font(.caption2)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 2)
                        .background(Color.gray.opacity(0.2))
                        .clipShape(RoundedRectangle(cornerRadius: 3))
                }

                if let epistemicStatus = claim.epistemicStatus {
                    Text(epistemicStatus.rawValue.capitalized)
                        .font(.caption2)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 2)
                        .background(statusColor.opacity(0.2))
                        .foregroundStyle(statusColor)
                        .clipShape(RoundedRectangle(cornerRadius: 3))
                }
            }
        }
        .padding(10)
        .background(Color(.windowBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private var statusColor: Color {
        guard let status = claim.epistemicStatus else { return .gray }
        switch status {
        case .confirmed: return .green
        case .rejected: return .red
        case .tentative: return .orange
        }
    }
}

// MARK: - Flow Layout

struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = FlowResult(in: proposal.width ?? 0, subviews: subviews, spacing: spacing)
        return result.size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = FlowResult(in: bounds.width, subviews: subviews, spacing: spacing)
        for (index, subview) in subviews.enumerated() {
            subview.place(at: CGPoint(x: bounds.minX + result.positions[index].x,
                                       y: bounds.minY + result.positions[index].y),
                          proposal: .unspecified)
        }
    }

    struct FlowResult {
        var size: CGSize = .zero
        var positions: [CGPoint] = []

        init(in maxWidth: CGFloat, subviews: Subviews, spacing: CGFloat) {
            var posX: CGFloat = 0
            var posY: CGFloat = 0
            var rowHeight: CGFloat = 0

            for subview in subviews {
                let size = subview.sizeThatFits(.unspecified)
                if posX + size.width > maxWidth, posX > 0 {
                    posX = 0
                    posY += rowHeight + spacing
                    rowHeight = 0
                }
                positions.append(CGPoint(x: posX, y: posY))
                rowHeight = max(rowHeight, size.height)
                posX += size.width + spacing
            }

            self.size = CGSize(width: maxWidth, height: posY + rowHeight)
        }
    }
}

// MARK: - Previews

#Preview("Browser") {
    OntologyBrowser()
        .frame(width: 600, height: 500)
}

#Preview("Entity Row") {
    List {
        EntityRow(entity: Components.Schemas.EntityCoreference(
            entityId: "entity-1",
            canonicalName: "Napoleon Bonaparte",
            entityType: .person,
            aliases: ["The Emperor", "Napoleon I"],
            description: nil,
            language: "fr",
            metadata: nil,
            mergedIntoId: nil
        ))
    }
    .listStyle(.sidebar)
}
