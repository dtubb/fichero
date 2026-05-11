import FicheroAPIClient
import SwiftUI

// MARK: - Entity Detail View

struct EntityDetailView: View {
    let entity: Components.Schemas.KnowledgeEntity
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
                    .foregroundStyle(Color.accentColor)

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
