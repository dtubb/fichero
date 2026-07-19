import FicheroAPIClient
import Foundation
import SwiftUI

// MARK: - Aliases / metadata panels + entity-type mapping

extension EntityDetailView {
    static func prettyMetadataJSON(_ entity: Components.Schemas.KnowledgeEntity) -> String {
        let raw = entity.metadata?.additionalProperties.value ?? [:]
        guard JSONSerialization.isValidJSONObject(raw),
              let data = try? JSONSerialization.data(withJSONObject: raw, options: [.prettyPrinted, .sortedKeys]),
              let text = String(data: data, encoding: .utf8)
        else {
            return "{}"
        }
        return text
    }

    /// Map EntityType → the search-scope token consumed by
    /// runToolbarSearch via the entity-search notification. Mirrors
    /// what the library entity lozenges use so tapping a name here
    /// hits the same artifact bucket.
    var entitySearchScope: String {
        guard let type = entity.entityType else { return "" }
        switch type {
        case .person: return "people"
        case .location: return "places"
        case .organization: return "organizations"
        case .event: return "events"
        case .concept: return "keywords"
        case .citation: return "citations"
        case .other: return ""
        }
    }

    var iconForEntityType: String {
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

    // MARK: - Aliases

    var aliasesSection: some View {
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
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - Raw entity JSON

    var metadataSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Raw Entity JSON")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                if let metadataSaveMessage {
                    Text(metadataSaveMessage)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Button {
                    Task { await saveMetadataJSON() }
                } label: {
                    if isSavingMetadata {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Text("Save")
                    }
                }
                .disabled(isSavingMetadata)
            }

            TextEditor(text: $metadataJSON)
                .font(.system(.caption, design: .monospaced))
                .frame(minHeight: 120)
                .padding(6)
                .background(Color(.textBackgroundColor))
                .clipShape(RoundedRectangle(cornerRadius: 6))
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}
