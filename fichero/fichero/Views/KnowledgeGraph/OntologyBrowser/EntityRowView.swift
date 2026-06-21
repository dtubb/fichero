import FicheroAPIClient
import SwiftUI

// MARK: - Entity Row

/// Shared renderer for a single `KnowledgeEntity` row. One component, two
/// presentations so the OntologyBrowser sidebar and the researcher-facing
/// EntityDigestView index share one code path instead of bespoke duplicates
/// (#1690). The compact artifact-string chips (`EntityLozenge` /
/// `ArtifactEntityCell`) are intentionally NOT folded in here — they render
/// raw artifact extraction strings, not a `KnowledgeEntity`.
struct EntityRow: View {
    /// Visual presentation.
    /// - `.browser`: the OntologyBrowser curation-sidebar look — type icon,
    ///   subheadline name + aliases subtitle, accent claim-count pill, and a
    ///   trailing type chip.
    /// - `.digest`: the EntityDigestView "published" look — no icon,
    ///   body-weight name, capitalized-type subtitle, and an "N sources"
    ///   secondary capsule.
    enum Style {
        case browser
        case digest
    }

    let entity: Components.Schemas.KnowledgeEntity
    var claimCount: Int = 0
    var style: Style = .browser

    var body: some View {
        switch style {
        case .browser: browserBody
        case .digest: digestBody
        }
    }

    /// Canonical name to render, with a safe fallback when canonicalName is
    /// empty or whitespace-only (guards against upstream extraction noise).
    var displayLabelForTesting: String { displayLabel }

    private var displayLabel: String {
        let name = entity.canonicalName.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else {
            let typeStr = entity.entityType?.rawValue ?? "entity"
            let idSuffix = entity.id.map { String($0.suffix(6)) } ?? "?"
            return "\(typeStr) ·\(idSuffix)"
        }
        return name
    }

    private var browserBody: some View {
        HStack(spacing: 8) {
            Image(systemName: iconForEntityType)
                .foregroundStyle(colorForEntityType)
                .frame(width: 16)

            VStack(alignment: .leading, spacing: 2) {
                Text(displayLabel)
                    .font(.subheadline.weight(.medium))
                    .lineLimit(1)

                if let aliases = entity.aliases, !aliases.isEmpty {
                    Text(aliases.prefix(2).joined(separator: " · "))
                        .font(.caption)
                        .foregroundStyle(.tertiary)
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

    private var digestBody: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(displayLabel)
                    .font(.body)
                if let type = entity.entityType {
                    Text(type.rawValue.capitalized)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            Text("\(claimCount) sources")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Capsule().fill(Color.secondary.opacity(0.1)))
        }
    }

    private var colorForEntityType: Color {
        guard let type = entity.entityType else { return .secondary }
        switch type {
        case .person: return .blue
        case .organization: return .orange
        case .location: return .green
        case .event: return .red
        case .concept: return .purple
        case .citation: return .brown
        case .other: return .secondary
        }
    }

    private var iconForEntityType: String {
        guard let type = entity.entityType else { return "person.fill" }
        switch type {
        case .person: return "person.fill"
        case .organization: return "building.2.fill"
        case .location: return "mappin.circle.fill"
        case .event: return "calendar.circle.fill"
        case .concept: return "lightbulb.fill"
        case .citation: return "text.quote"
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
        case .citation: return "citation"
        case .other: return "other"
        }
    }
}
