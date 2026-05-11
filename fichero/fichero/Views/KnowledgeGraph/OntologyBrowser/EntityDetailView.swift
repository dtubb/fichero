import FicheroAPIClient
import SwiftUI

// MARK: - Entity Detail View

struct EntityDetailView: View {
    let entity: Components.Schemas.KnowledgeEntity
    let claims: [Components.Schemas.KnowledgeClaim]
    let isLoadingClaims: Bool

    /// CSV of hidden EpistemicStatus raw values. Shared with the rest
    /// of the KG views so a setting in one place persists everywhere
    /// (peer to inspector.kg.hiddenKinds). (#892/#893)
    @AppStorage("inspector.kg.hiddenEpistemic")
    private var hiddenEpistemicCSV: String = ""

    /// CSV of hidden ClaimType raw values — the ontological axis.
    @AppStorage("inspector.kg.hiddenClaimTypes")
    private var hiddenClaimTypesCSV: String = ""

    private var hiddenEpistemic: Set<String> {
        Self.parseCSV(hiddenEpistemicCSV)
    }
    private var hiddenClaimTypes: Set<String> {
        Self.parseCSV(hiddenClaimTypesCSV)
    }

    /// Pure helper exposed for tests.
    static func parseCSV(_ csv: String) -> Set<String> {
        Set(csv.split(separator: ",").map(String.init).filter { !$0.isEmpty })
    }

    /// Pure helper exposed for tests — filter claims by both axes.
    /// Nil epistemic/claim_type values are treated as "tentative" and
    /// "fact" respectively (the model defaults) so an unclassified
    /// claim doesn't disappear under the default filters.
    static func filterClaims(
        _ claims: [Components.Schemas.KnowledgeClaim],
        hiddenEpistemic: Set<String>,
        hiddenClaimTypes: Set<String>
    ) -> [Components.Schemas.KnowledgeClaim] {
        guard !hiddenEpistemic.isEmpty || !hiddenClaimTypes.isEmpty else { return claims }
        return claims.filter { claim in
            let epi = claim.epistemicStatus?.rawValue ?? "tentative"
            let kind = claim.claimType?.rawValue ?? "fact"
            return !hiddenEpistemic.contains(epi) && !hiddenClaimTypes.contains(kind)
        }
    }

    private var filteredClaims: [Components.Schemas.KnowledgeClaim] {
        Self.filterClaims(
            claims,
            hiddenEpistemic: hiddenEpistemic,
            hiddenClaimTypes: hiddenClaimTypes
        )
    }

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
                    Text(claimsCountLabel)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            // Twin filter strips — epistemic (how firmly asserted) +
            // ontological / claim_type (what kind of knowledge). Both
            // axes shipped in #892. @AppStorage persists across views.
            if !claims.isEmpty {
                filterStrips
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
            } else if filteredClaims.isEmpty {
                Text("All \(claims.count) claims filtered out — toggle chips above to reveal")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 12)
            } else {
                ForEach(filteredClaims.prefix(10), id: \.id) { claim in
                    ClaimSummaryCard(claim: claim)
                }

                if filteredClaims.count > 10 {
                    Text("+ \(filteredClaims.count - 10) more claims")
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

    private var claimsCountLabel: String {
        let total = claims.count
        let shown = filteredClaims.count
        return shown == total ? "\(total)" : "\(shown) / \(total)"
    }

    // MARK: - Filter chips

    private var filterStrips: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 4) {
                Text("Status")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .frame(width: 56, alignment: .leading)
                ForEach(["confirmed", "tentative", "rejected"], id: \.self) { key in
                    chip(label: key.capitalized,
                         isHidden: hiddenEpistemic.contains(key),
                         color: epistemicColor(key)) {
                        toggle(key, in: &hiddenEpistemicCSV)
                    }
                }
                Spacer(minLength: 0)
            }
            HStack(spacing: 4) {
                Text("Kind")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .frame(width: 56, alignment: .leading)
                ForEach(["fact", "analysis", "interpretation", "argument", "historiography", "theory"], id: \.self) { key in
                    chip(label: key.capitalized,
                         isHidden: hiddenClaimTypes.contains(key),
                         color: .gray) {
                        toggle(key, in: &hiddenClaimTypesCSV)
                    }
                }
                Spacer(minLength: 0)
            }
        }
    }

    private func chip(label: String, isHidden: Bool, color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.caption2)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background((isHidden ? Color.gray : color).opacity(isHidden ? 0.1 : 0.25))
                .foregroundStyle(isHidden ? .secondary : .primary)
                .clipShape(RoundedRectangle(cornerRadius: 3))
        }
        .buttonStyle(.plain)
    }

    private func epistemicColor(_ raw: String) -> Color {
        switch raw {
        case "confirmed": return .green
        case "rejected": return .red
        case "tentative": return .orange
        default: return .gray
        }
    }

    private func toggle(_ key: String, in csv: inout String) {
        var set = Self.parseCSV(csv)
        if set.contains(key) { set.remove(key) } else { set.insert(key) }
        csv = set.sorted().joined(separator: ",")
    }
}
