import FicheroAPIClient
import SwiftUI

// MARK: - Entity Row

struct EntityRow: View {
    let entity: Components.Schemas.KnowledgeEntity
    var claimCount: Int = 0

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

            Spacer(minLength: 6)

            if claimCount > 0 {
                Text("\(claimCount)")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.white)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.accentColor.opacity(0.75))
                    .clipShape(Capsule())
            }

            Text(entityTypeLabel)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.secondary.opacity(0.12))
                .clipShape(RoundedRectangle(cornerRadius: 6))
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

    private var entityTypeLabel: String {
        guard let type = entity.entityType else { return "other" }
        switch type {
        case .person: return "person"
        case .organization: return "org"
        case .location: return "place"
        case .event: return "event"
        case .concept: return "concept"
        case .other: return "other"
        }
    }
}
