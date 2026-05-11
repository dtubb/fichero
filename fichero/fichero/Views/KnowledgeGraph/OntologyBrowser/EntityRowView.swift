import FicheroAPIClient
import SwiftUI

// MARK: - Entity Row

struct EntityRow: View {
    let entity: Components.Schemas.KnowledgeEntity

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
        case .concept: return "lightbulb.fill"
        case .other: return "circle.fill"
        }
    }
}
