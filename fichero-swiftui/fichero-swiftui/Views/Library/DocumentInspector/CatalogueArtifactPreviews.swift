import SwiftUI

/// Structured previews for the per-section artifacts produced by the
/// Catalogue workflow (people, dates, rivers, events, mines, properties,
/// keywords). Each catalogue-section artifact stores its structured items
/// in `artifact.data["items"]` as an array of dicts; these views render
/// them as compact tables the inspector can show without a separate sheet.
enum CatalogueArtifactPreviews {

    static func items(from data: [String: AnyCodable]) -> [[String: Any]] {
        guard let value = data["items"]?.value,
              let array = value as? [[String: Any]] else {
            return []
        }
        return array
    }

    @ViewBuilder
    static func nameContext(
        _ data: [String: AnyCodable],
        primaryKey: String
    ) -> some View {
        let items = items(from: data)
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    if let name = item[primaryKey] as? String {
                        HStack(alignment: .top, spacing: 6) {
                            Text(name)
                                .font(.caption.weight(.medium))
                                .foregroundColor(.primary)
                                .frame(minWidth: 100, alignment: .leading)
                            if let context = item["contexto"] as? String, !context.isEmpty {
                                Text(context)
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                                    .lineLimit(3)
                            }
                        }
                    }
                }
            }
            .padding(6)
            .background(Color(.textBackgroundColor))
            .cornerRadius(4)
        }
    }

    @ViewBuilder
    static func dates(_ data: [String: AnyCodable]) -> some View {
        let items = items(from: data)
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    let normalized = (item["fecha_normalizada"] as? String) ?? ""
                    let raw = (item["fecha"] as? String) ?? ""
                    let context = (item["contexto"] as? String) ?? ""
                    HStack(alignment: .top, spacing: 6) {
                        Text(normalized.isEmpty ? raw : normalized)
                            .font(.caption.monospacedDigit())
                            .foregroundColor(.primary)
                            .frame(minWidth: 100, alignment: .leading)
                        if !context.isEmpty {
                            Text(context)
                                .font(.caption2)
                                .foregroundColor(.secondary)
                                .lineLimit(3)
                        }
                    }
                }
            }
            .padding(6)
            .background(Color(.textBackgroundColor))
            .cornerRadius(4)
        }
    }

    @ViewBuilder
    static func rivers(_ data: [String: AnyCodable]) -> some View {
        let items = items(from: data)
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    let name = (item["nombre"] as? String) ?? ""
                    let alts = (item["ortografias_alternativas"] as? [String]) ?? []
                    let context = (item["contexto"] as? String) ?? ""
                    VStack(alignment: .leading, spacing: 1) {
                        Text(name)
                            .font(.caption.weight(.medium))
                            .foregroundColor(.primary)
                        if !alts.isEmpty {
                            Text("Alt: \(alts.joined(separator: ", "))")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                        if !context.isEmpty {
                            Text(context)
                                .font(.caption2)
                                .foregroundColor(.secondary)
                                .lineLimit(2)
                        }
                    }
                }
            }
            .padding(6)
            .background(Color(.textBackgroundColor))
            .cornerRadius(4)
        }
    }

    @ViewBuilder
    static func keywords(_ data: [String: AnyCodable]) -> some View {
        if let value = data["keywords"]?.value,
           let keywords = value as? [String],
           !keywords.isEmpty {
            Text(keywords.joined(separator: " • "))
                .font(.caption2)
                .foregroundColor(.primary)
                .padding(6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.accentColor.opacity(0.1))
                .cornerRadius(4)
                .textSelection(.enabled)
        }
    }
}
