import FicheroAPIClient
import SwiftUI

// MARK: - Entity Detail View

struct EntityDetailView: View {
    @Environment(EntityServiceGenerated.self) var entityService
    @Environment(ClaimStore.self) var claimStore
    /// Entity rename routes through the store (#1862/#1865); the change-stream's
    /// `entity.updated` event fans the refresh, retiring `.ficheroEntityUpdated`.
    @Environment(EntityStore.self) var entityStore
    let entity: Components.Schemas.KnowledgeEntity
    let claims: [Components.Schemas.KnowledgeClaim]
    let isLoadingClaims: Bool
    var onNavigateToSource: ((Components.Schemas.KnowledgeClaim) -> Void)?

    init(
        entity: Components.Schemas.KnowledgeEntity,
        claims: [Components.Schemas.KnowledgeClaim],
        isLoadingClaims: Bool,
        onNavigateToSource: ((Components.Schemas.KnowledgeClaim) -> Void)? = nil
    ) {
        self.entity = entity
        self.claims = claims
        self.isLoadingClaims = isLoadingClaims
        self.onNavigateToSource = onNavigateToSource
    }

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
    @State var metadataJSON: String = "{}"
    @State var metadataSaveMessage: String?
    @State var isSavingMetadata = false
    @State private var showDigestSheet = false
    @State var showContradictionTriageSheet = false
    @State var showClaimReviewQueueSheet = false

    /// Possible-duplicate candidates for this entity (#3317) from embedding
    /// similarity. Review-only: a merge is always an explicit user action.
    @State var duplicateCandidates: [DuplicateCandidate] = []
    @State var isLoadingDuplicates = false
    @State var duplicateActionMessage: String?

    /// Native multi-select for the claims (source-annotation SVO) List. (#1864)
    @State var selectedClaimIds: Set<String> = []
    @State var claimsToDelete: [Components.Schemas.KnowledgeClaim] = []
    @State var showingDeleteClaimsConfirmation: Bool = false

    /// In-place rename of the entity from the header. Optimistic local
    /// override while the PATCH is in flight; reverts on failure. (#1865)
    @State private var isRenamingHeader = false
    @State private var renameDraft = ""
    @State private var nameOverride: String?
    @FocusState private var renameFieldFocused: Bool

    /// Canonical name to display — the optimistic override wins while a
    /// rename is committing, otherwise the server's value.
    var displayName: String {
        nameOverride ?? entity.canonicalName
    }

    var body: some View {
        if sourceGroupsMode {
            VStack(spacing: 0) {
                sourceGroupsTopBar
                Divider()
                EntitySourceGroupsView(entityId: entity.id ?? "")
            }
        } else {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    headerSection
                    aliasesSection
                    possibleDuplicatesSection
                    mentionsSection
                    metadataSection
                    if Self.showsClaimsSection(for: entity) {
                        claimsSection
                    }
                    auditSection
                    EntityNotesSection(entityId: entity.id ?? "")
                }
                .padding()
            }
            .task(id: entity.id) {
                metadataJSON = Self.prettyMetadataJSON(entity)
                await loadAudits()
                await loadDuplicateCandidates()
            }
        }
    }

    static func showsClaimsSection(
        for entity: Components.Schemas.KnowledgeEntity
    ) -> Bool {
        entity.entityType != .location
    }

    // MARK: - Source-groups top bar

    private var sourceGroupsTopBar: some View {
        HStack {
            Image(systemName: iconForEntityType)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(displayName)
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
        .background(.regularMaterial)
    }

    // MARK: - Header

    /// Canonical-name view. Double-click or the Rename context action
    /// swaps the link for an inline TextField (Enter commits, Esc
    /// cancels); otherwise it's a tappable scoped-search link. (#1864/#1865)
    @ViewBuilder
    private var headerNameView: some View {
        if isRenamingHeader {
            TextField("Entity name", text: $renameDraft)
                .textFieldStyle(.plain)
                .font(.title2)
                .fontWeight(.semibold)
                .focused($renameFieldFocused)
                .onSubmit { commitRename() }
                #if os(macOS)
                .onExitCommand { cancelRename() }
                #endif
                .onAppear { renameFieldFocused = true }
        } else {
            Button {
                // #882 — tap canonical name to run a scoped library search.
                EntitySearchState.shared.request(
                    name: displayName,
                    entityType: entitySearchScope
                )
            } label: {
                Text(displayName)
                    .font(.title2)
                    .fontWeight(.semibold)
                    .foregroundStyle(Color.accentColor)
                    .underline()
            }
            .buttonStyle(.plain)
            .help("Search the library for \"\(displayName)\" — double-click to rename")
            .simultaneousGesture(TapGesture(count: 2).onEnded { beginRename() })
            .contextMenu {
                Button("Rename") { beginRename() }
            }
        }
    }

    private func beginRename() {
        renameDraft = displayName
        isRenamingHeader = true
    }

    private func cancelRename() {
        isRenamingHeader = false
        renameFieldFocused = false
    }

    /// Commit the inline rename through the typed entity service.
    /// Optimistic: the new name shows immediately; a failed PATCH reverts.
    private func commitRename() {
        let trimmed = renameDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        isRenamingHeader = false
        renameFieldFocused = false
        guard !trimmed.isEmpty, trimmed != displayName, let entityId = entity.id else { return }
        let previous = nameOverride
        nameOverride = trimmed
        Task {
            do {
                // Route through the store; its scope reload + the change-stream's
                // `entity.updated` event refresh every bound surface (#1862/#1865).
                _ = try await entityStore.rename(entityId: entityId, to: trimmed)
            } catch {
                nameOverride = previous
            }
        }
    }

    // MARK: - Header

    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: iconForEntityType)
                    .font(.system(size: 24))
                    .foregroundStyle(Color.accentColor)

                headerNameView

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
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .sheet(isPresented: $showDigestSheet) {
            EntityDigestContent(entity: entity, entityService: entityService)
                .frame(minWidth: 780, minHeight: 560)
                .padding(20)
        }
    }
}
