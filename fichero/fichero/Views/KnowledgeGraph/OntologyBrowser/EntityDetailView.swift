import FicheroAPIClient
import SwiftUI

// MARK: - Entity Detail View

struct EntityDetailView: View { // swiftlint:disable:this type_body_length
    let entity: Components.Schemas.KnowledgeEntity
    let claims: [Components.Schemas.KnowledgeClaim]
    let isLoadingClaims: Bool

    /// Curation audit log for this entity — populated lazily from
    /// `/api/kg/entity-curation/audit?entity_id=…`. Each row is a
    /// reversible merge/split operation. Empty list = no curation has
    /// happened yet (the common case until a reviewer touches the entity).
    @State private var audits: [Components.Schemas.EntityAuditResponse] = []
    @State private var isLoadingAudits: Bool = false

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

    /// Toggle for the reconstructed-paragraph view. When ON, the claims
    /// section renders as flowing prose; when OFF, individual claim
    /// cards. Persisted per-window so the user can pick their default
    /// reading mode. (#989)
    @SceneStorage("entity.biographyMode") private var biographyMode: Bool = false

    /// Source-groups mode: replace the whole detail body with
    /// EntitySourceGroupsView (claims grouped by source doc/page).
    /// Persisted per-window. (#1183)
    @SceneStorage("entity.sourceGroupsMode") private var sourceGroupsMode: Bool = false

    /// Show all filtered claims vs the default top-10 cap. Per-window
    /// state via @SceneStorage so resets on each entity navigation
    /// don't surprise the user. (#994)
    @State private var showAllClaims: Bool = false

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
                    claimsSection
                    auditSection
                }
                .padding()
            }
            .task(id: entity.id) {
                await loadAudits()
            }
        }
    }

    /// Reconstructed biographical paragraph — composes each filtered
    /// claim's SVO triple into a prose sentence with the source doc
    /// inline. After the first mention of the subject, subsequent
    /// sentences swap to a pronoun ("he"/"she"/"they"/"it") based on
    /// entity type. Source citations are caption-sized + italic +
    /// tappable to open the source via ficheroOpenClaimSource. (#989)
    @ViewBuilder
    private var biographySection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Biography")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                Text("Reconstructed from claims")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            biographyComposedText
                .font(.body)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    /// Build the prose paragraph. Iterates filteredClaims that have an
    /// SVO triple in metadata, substitutes a pronoun after the first
    /// subject mention, appends an italic doc-name citation per
    /// sentence. Returns Text(verbatim) so we keep AttributedString
    /// styling for the verb (italic) + citation (italic secondary).
    private var biographyComposedText: Text {
        let pronoun = entityPronoun
        var first = true
        var composed = Text("")
        for claim in filteredClaims {
            guard let svo = svoOf(claim) else { continue }
            let subject = first ? svo.subject : pronoun
            first = false
            let docName = LibraryManager.shared.globalLibrary?
                .documentStore
                .currentDocuments
                .first(where: { $0.id == claim.sourceDocumentId })?
                .name
            let citation: String = {
                let parts = [docName, claim.sourcePageLabel.flatMap { "p. \($0)" }]
                    .compactMap { $0 }
                return parts.isEmpty ? "" : " [\(parts.joined(separator: ", "))]"
            }()
            composed = composed
                + Text(subject)
                + Text(" \(svo.verb) ").italic().foregroundColor(.accentColor)
                + Text(svo.object)
                + Text(citation)
                    .font(.caption2)
                    .italic()
                    .foregroundColor(.secondary)
                + Text(". ")
        }
        if first {
            // No SVO-shaped claims to compose.
            return Text("No subject-verb-object claims to compose a biography from.")
                .foregroundColor(.secondary)
                .italic()
        }
        return composed
    }

    private struct SVOTriple {
        let subject: String
        let verb: String
        let object: String
    }

    /// Returns the SVO triple from claim metadata, or nil if the claim
    /// has no SVO (legacy or empty-content). Mirrors the helper on
    /// ClaimSummaryCard.
    private func svoOf(
        _ claim: Components.Schemas.KnowledgeClaim
    ) -> SVOTriple? {
        // Prefer typed top-level fields (#984); legacy metadata fallback.
        let subject = (claim.subjectCanonical ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let verb = (claim.predicateVerb ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let object = (claim.objectPhrase ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if !subject.isEmpty, !verb.isEmpty, !object.isEmpty {
            return SVOTriple(subject: subject, verb: verb, object: object)
        }
        guard let dict = claim.metadata?.additionalProperties.value else { return nil }
        let metadataSubject = (dict["subject"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let metadataVerb = (dict["verb"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let metadataObject = (dict["object"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !metadataSubject.isEmpty, !metadataVerb.isEmpty, !metadataObject.isEmpty else { return nil }
        return SVOTriple(subject: metadataSubject, verb: metadataVerb, object: metadataObject)
    }

    /// Pronoun to use after the first mention. Defaults to "they" for
    /// neutrality on Person; "it" for non-persons.
    private var entityPronoun: String {
        guard let type = entity.entityType else { return "it" }
        switch type {
        case .person: return "they"
        default: return "it"
        }
    }

    /// Curation history surfaced from /api/kg/entity-curation/audit.
    /// Only renders when there's a history — keeps the panel tight for
    /// the 95% case where the entity hasn't been merged/split yet.
    @ViewBuilder
    private var auditSection: some View {
        if isLoadingAudits {
            HStack {
                ProgressView().scaleEffect(0.7)
                Text("Loading curation history…")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal)
        } else if !audits.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Curation History")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                ForEach(audits, id: \.id) { audit in
                    auditRow(audit)
                }
            }
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(.controlBackgroundColor))
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
    }

    private func auditRow(_ audit: Components.Schemas.EntityAuditResponse) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: auditIcon(audit.operationType))
                .foregroundStyle(auditTint(audit.operationType))
                .frame(width: 16)
            VStack(alignment: .leading, spacing: 2) {
                Text(auditLabel(audit))
                    .font(.caption)
                Text(audit.createdAt, style: .relative)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            Text(audit.createdBy)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 2)
    }

    private func auditIcon(_ mergeOp: Components.Schemas.EntityMergeOperationType) -> String {
        switch mergeOp {
        case .merge: return "arrow.triangle.merge"
        case .split: return "arrow.triangle.branch"
        case .undoMerge, .undoSplit: return "arrow.uturn.backward.circle"
        }
    }

    private func auditTint(_ mergeOp: Components.Schemas.EntityMergeOperationType) -> Color {
        switch mergeOp {
        case .merge: return .blue
        case .split: return .orange
        case .undoMerge, .undoSplit: return .gray
        }
    }

    private func auditLabel(_ audit: Components.Schemas.EntityAuditResponse) -> String {
        switch audit.operationType {
        case .merge:
            return "Absorbed \(audit.sourceEntityIds.count) entity\(audit.sourceEntityIds.count == 1 ? "" : "s")"
        case .split:
            return "Split off \(audit.sourceEntityIds.count) entity\(audit.sourceEntityIds.count == 1 ? "" : "s")"
        case .undoMerge:
            return "Undid earlier merge"
        case .undoSplit:
            return "Undid earlier split"
        }
    }

    private func loadAudits() async {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        isLoadingAudits = true
        defer { isLoadingAudits = false }
        do {
            audits = try await library.entityService.listEntityAudits(entityId: entity.id, limit: 25)
        } catch {
            audits = []
        }
    }

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

                // Toggle the biography (reconstructed-paragraph) view
                // on/off. Off by default — the claim cards are the
                // canonical surface; biography is a reading affordance.
                // (#989)
                Button {
                    biographyMode.toggle()
                } label: {
                    Image(systemName: biographyMode
                          ? "text.alignleft"
                          : "text.justify")
                        .font(.caption)
                        .foregroundStyle(biographyMode ? Color.accentColor : Color.secondary)
                }
                .buttonStyle(.plain)
                .help(biographyMode ? "Hide biography paragraph" : "Show biography paragraph")

                // Source-groups mode: switch to per-source-document
                // grouped prose view backed by the entity inspector
                // endpoint. (#1183)
                Button {
                    sourceGroupsMode = true
                } label: {
                    Image(systemName: "doc.text.magnifyingglass")
                        .font(.caption)
                        .foregroundStyle(Color.secondary)
                }
                .buttonStyle(.plain)
                .help("View claims grouped by source document")

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
            } else if biographyMode {
                biographyComposedText
                    .font(.body)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            } else {
                // LazyVStack so the inspector stays at 60fps even when
                // an entity has hundreds of claims (real corpora hit
                // this on hub entities). Cap at 10 visible by default;
                // "show all" toggle reveals the rest in the same lazy
                // container. (#994 + #989 follow-up)
                let cap = 10
                let visibleClaims = showAllClaims
                    ? Array(filteredClaims)
                    : Array(filteredClaims.prefix(cap))
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(visibleClaims, id: \.id) { claim in
                        ClaimSummaryCard(claim: claim)
                    }
                }
                if filteredClaims.count > cap {
                    Button {
                        showAllClaims.toggle()
                    } label: {
                        Text(showAllClaims
                             ? "Show \(cap) of \(filteredClaims.count)"
                             : "Show all \(filteredClaims.count) claims")
                            .font(.caption)
                            .foregroundColor(.accentColor)
                    }
                    .buttonStyle(.plain)
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
        // Show only chips for status / kind values that ACTUALLY appear
        // in this entity's claims. Computed from the unfiltered `claims`
        // (not `filteredClaims`) so hiding the only Confirmed claim
        // still leaves the Confirmed chip visible to un-hide. (#1005)
        let presentEpistemic: Set<String> = Set(claims.map {
            $0.epistemicStatus?.rawValue ?? "tentative"
        })
        let presentKinds: Set<String> = Set(claims.map {
            $0.claimType?.rawValue ?? "fact"
        })
        let statusKeys = ["confirmed", "tentative", "rejected"].filter {
            presentEpistemic.contains($0)
        }
        let kindKeys = ["fact", "analysis", "interpretation", "argument", "historiography", "theory"].filter {
            presentKinds.contains($0)
        }
        return VStack(alignment: .leading, spacing: 4) {
            if !statusKeys.isEmpty {
                HStack(spacing: 4) {
                    Text("Status")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .frame(width: 56, alignment: .leading)
                    ForEach(statusKeys, id: \.self) { key in
                        chip(label: key.capitalized,
                             isHidden: hiddenEpistemic.contains(key),
                             color: epistemicColor(key)) {
                            toggle(key, in: &hiddenEpistemicCSV)
                        }
                    }
                    Spacer(minLength: 0)
                }
            }
            if !kindKeys.isEmpty {
                HStack(spacing: 4) {
                    Text("Kind")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .frame(width: 56, alignment: .leading)
                    ForEach(kindKeys, id: \.self) { key in
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

    /// Hide visually-degraded OCR strings that are mostly replacement
    /// glyphs; keeps the detail panel readable when extraction quality
    /// is poor on a page.
    private func cleanedDisplayText(_ value: String?) -> String? {
        guard let raw = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              !raw.isEmpty else { return nil }
        let replacementGlyphs = raw.filter { $0 == "\u{FFFD}" || $0 == "□" || $0 == "�" }
        if !raw.isEmpty {
            let ratio = Double(replacementGlyphs.count) / Double(raw.count)
            if ratio > 0.08 { return nil }
        }
        return raw
    }
}
