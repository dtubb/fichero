import FicheroAPIClient
import SwiftUI

// MARK: - Entity Detail View

struct EntityDetailView: View {
    @EnvironmentObject private var entityService: EntityServiceGenerated
    let entity: Components.Schemas.KnowledgeEntity
    let claims: [Components.Schemas.KnowledgeClaim]
    let isLoadingClaims: Bool
    var onNavigateToSource: ((Components.Schemas.KnowledgeClaim) -> Void)? = nil

    /// Curation audit log for this entity — populated lazily from
    /// `/api/kg/entity-curation/audit?entity_id=…`. Each row is a
    /// reversible merge/split operation. Empty list = no curation has
    /// happened yet (the common case until a reviewer touches the entity).
    @State var audits: [Components.Schemas.EntityAuditResponse] = []
    @State var isLoadingAudits: Bool = false
    @State var undoingAuditId: String?
    @State var auditStatusMessage: String?

    /// CSV of hidden EpistemicStatus raw values. Shared with the rest
    /// of the KG views so a setting in one place persists everywhere
    /// (peer to inspector.kg.hiddenKinds). (#892/#893)
    @AppStorage("inspector.kg.hiddenEpistemic")
    var hiddenEpistemicCSV: String = ""

    /// CSV of hidden ClaimType raw values — the ontological axis.
    @AppStorage("inspector.kg.hiddenClaimTypes")
    var hiddenClaimTypesCSV: String = ""

    var hiddenEpistemic: Set<String> {
        Self.parseCSV(hiddenEpistemicCSV)
    }

    var hiddenClaimTypes: Set<String> {
        Self.parseCSV(hiddenClaimTypesCSV)
    }

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

    var filteredClaims: [Components.Schemas.KnowledgeClaim] {
        Self.filterClaims(
            claims,
            hiddenEpistemic: hiddenEpistemic,
            hiddenClaimTypes: hiddenClaimTypes
        )
    }

    /// Toggle for the reconstructed-paragraph view. When ON, the claims
    /// section renders as flowing prose; when OFF, individual claim
    /// cards. Persisted per-window so the user can pick their default
    /// reading mode. (#989)
    @SceneStorage("entity.biographyMode") var biographyMode: Bool = false

    /// Source-groups mode: replace the whole detail body with
    /// EntitySourceGroupsView (claims grouped by source doc/page).
    /// Persisted per-window. (#1183)
    @SceneStorage("entity.sourceGroupsMode") var sourceGroupsMode: Bool = false

    /// Show all filtered claims vs the default top-10 cap. Per-window
    /// state via @SceneStorage so resets on each entity navigation
    /// don't surprise the user. (#994)
    @State var showAllClaims: Bool = false
    @State private var metadataJSON: String = "{}"
    @State private var metadataSaveMessage: String?
    @State private var isSavingMetadata = false
    @State private var showDigestSheet = false

    var body: some View {
        if sourceGroupsMode {
            VStack(spacing: 0) {
                // Minimal top bar: entity name + back button
                HStack {
                    Image(systemName: iconForEntityType)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(entity.canonicalName)
                        .font(.caption)
                        .fontWeight(.semibold)
                        .lineLimit(1)
                    Spacer()
                    Button {
                        sourceGroupsMode = false
                    } label: {
                        Label("Claims", systemImage: "list.bullet")
                            .font(.caption2)
                            .foregroundStyle(Color.accentColor)
                    }
                    .buttonStyle(.plain)
                    .help("Back to claim cards")
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color(.windowBackgroundColor))
                Divider()
                EntitySourceGroupsView(entityId: entity.id ?? "")
            }
        } else {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    headerSection
                    aliasesSection
                    if biographyMode {
                        biographySection
                    }
                    metadataSection
                    claimsSection
                    auditSection
                }
                .padding()
            }
            .task(id: entity.id) {
                metadataJSON = Self.prettyMetadataJSON(entity)
                await loadAudits()
            }
        }
    }

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

    // MARK: - Header

    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: iconForEntityType)
                    .font(.system(size: 24))
                    .foregroundStyle(Color.accentColor)

                Button {
                    // #882 — tap canonical name to run a scoped library
                    // search. Pass entityType so ContentView's receiver
                    // takes the typed branch (e.g. `people:"Eugenio Córdoba"`)
                    // and hits only that artifact instead of free-text.
                    NotificationCenter.default.post(
                        name: .ficheroEntitySearchRequested,
                        object: nil,
                        userInfo: [
                            "name": entity.canonicalName,
                            "entityType": entitySearchScope
                        ]
                    )
                } label: {
                    Text(entity.canonicalName)
                        .font(.title2)
                        .fontWeight(.semibold)
                        .foregroundStyle(Color.accentColor)
                        .underline()
                }
                .buttonStyle(.plain)
                .help("Search the library for \"\(entity.canonicalName)\"")

                Spacer()

                Button {
                    showDigestSheet = true
                } label: {
                    Label("Digest", systemImage: "book.closed")
                        .font(.caption)
                }
                .buttonStyle(.bordered)
                .help("Open researcher digest view for this entity")
            }

            if let description = cleanedDisplayText(entity.description) {
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
        .sheet(isPresented: $showDigestSheet) {
            EntityDigestContent(entity: entity, entityService: entityService)
                .frame(minWidth: 780, minHeight: 560)
                .padding(20)
        }
    }

    /// Map EntityType → the search-scope token consumed by
    /// runToolbarSearch via the entity-search notification. Mirrors
    /// what the library entity lozenges use so tapping a name here
    /// hits the same artifact bucket.
    private var entitySearchScope: String {
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

    // MARK: - Aliases

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

    private var metadataSection: some View {
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
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func saveMetadataJSON() async {
        isSavingMetadata = true
        defer { isSavingMetadata = false }
        guard let library = LibraryManager.shared.globalLibrary else {
            metadataSaveMessage = "No library"
            return
        }
        let trimmed = metadataJSON.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let data = trimmed.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data),
              let dictAny = json as? [String: Any]
        else {
            metadataSaveMessage = "Invalid JSON object"
            return
        }
        var dict: [String: any Sendable] = [:]
        for (key, value) in dictAny {
            guard let sendable = value as? any Sendable else {
                metadataSaveMessage = "Unsupported JSON value"
                return
            }
            dict[key] = sendable
        }
        do {
            _ = try await library.entityService.patchEntity(entity.id, metadata: dict)
            metadataSaveMessage = "Saved"
        } catch {
            metadataSaveMessage = "Save failed"
        }
    }
}
