#if canImport(AppKit)
import AppKit
#endif
import FicheroAPIClient
import OSLog
import SwiftUI

// swiftlint:disable file_length

private let inspectorClaimsLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "KnowledgeGraphInspectorSection"
)

// Inspector section that shows knowledge-graph entities and claims for
// the currently selected document. Reads from `/api/claims` filtered
// by `source_document_id`, dereferences `entity_ids` against
// `/api/entities`, and groups by `EntityType` for display (#728).
//
// The legacy markdown-artifact previews (the old `DocumentInspectorArtifactsTab`
// struct and its JSON helpers) were removed in #1507 once routing moved to
// `DocumentInspectorContentV2`; this typed section is now the sole KG surface.
// swiftlint:disable:next type_body_length
struct KnowledgeGraphInspectorSection: View {
    let documentId: String
    let documentScope: InspectorClaimDocumentScope
    let entityService: EntityServiceGenerated
    let artifactService: ArtifactServiceGenerated
    let kgCurationService: KGCurationServiceGenerated
    /// Called when the user clicks the source-page arrow on an entity row.
    /// Receives the source page document id; ContentView decides how to
    /// navigate (typically: select the parent file in the grid). Optional
    /// so previews and standalone uses still compile. (#833)
    var onNavigateToSource: ((String) -> Void)?
    /// Called when the user clicks on a claim to select it for highlighting
    var onClaimSelect: ((String, String?, String?, String?, Int?, Int?) -> Void)?

    @Environment(KGFocusState.self) private var kgFocusState
    /// Observable claim store (#1862) — its `changeToken` bumps on every
    /// `claim.*` change event from the per-library change-stream, driving this
    /// section's resync. Replaces the retired `.ficheroClaim*` NotificationCenter
    /// bus; the inspector still owns its grouped KG read (iterate, never replace).
    @Environment(ClaimStore.self) private var claimStore
    @State private var loadState = KnowledgeGraphInspectorLoadState()
    @State private var claimSelection: Set<String> = []
    @State private var claimSelectionAnchor: String?
    @State private var isApplyingBulkAction = false
    @State private var isPruningTrivialClaims = false
    @State private var pendingMergePlan: InspectorClaimBulkSelection.MergePlan?
    @State private var pendingDeleteConfirmation: PendingClaimDeleteConfirmation?
    @State private var claimActionMessage: String?
    @State private var pendingPruneConfirmation: PendingPruneConfirmation?
    private var claims: [Components.Schemas.KnowledgeClaim] {
        get { loadState.claims }
        nonmutating set { loadState.claims = newValue }
    }
    private var canonicalGroups: [Components.Schemas.KGEntityGroup] {
        get { loadState.canonicalGroups }
        nonmutating set { loadState.canonicalGroups = newValue }
    }
    private var isLoading: Bool {
        get { loadState.isLoading }
        nonmutating set { loadState.isLoading = newValue }
    }
    private var loadError: String? {
        get { loadState.loadError }
        nonmutating set { loadState.loadError = newValue }
    }
    /// Comma-joined raw values of EntityKinds the user has hidden from the
    /// KG list. Persisted across launches so the filter survives restarts.
    /// Default: all kinds visible.
    @AppStorage("inspector.kg.hiddenKinds") private var hiddenKindsCSV: String = ""

    /// Text = dense semicolon prose per entity; List = grouped disclosure rows.
    @AppStorage("inspector.kg.displayMode") private var displayMode: KGDisplayMode = .text
    /// Default to the item's OWN records — a folder/PDF shows what belongs to
    /// IT, not its children's mixed in (#2697). Children are opt-in via the
    /// "Include children" scope toggle and badged ("Includes children") when on.
    @AppStorage("inspector.scope.includeChildren") private var includeChildren: Bool = false
    @AppStorage("editor.fontSize") private var defaultFontSize: Double = 13

    private var bodyTextFont: Font {
        .system(size: CGFloat(defaultFontSize))
    }

    private var typeLabelFont: Font {
        .system(size: CGFloat(max(defaultFontSize - 2, 9)), weight: .semibold)
    }

    private var hiddenKinds: Set<EntityKind> {
        Set(
            hiddenKindsCSV
                .split(separator: ",")
                .compactMap { EntityKind(rawValue: String($0)) }
        )
    }

    private var documentScopeLabel: String {
        documentScope.label
    }

    private var isMutatingClaims: Bool {
        isApplyingBulkAction || isPruningTrivialClaims
    }

    private var claimsById: [String: Components.Schemas.KnowledgeClaim] {
        Dictionary(uniqueKeysWithValues: claims.compactMap { claim in
            guard let id = claim.id else { return nil }
            return (id, claim)
        })
    }

    private func setHidden(_ kind: EntityKind, hidden: Bool) {
        var set = hiddenKinds
        if hidden { set.insert(kind) } else { set.remove(kind) }
        hiddenKindsCSV = set.map(\.rawValue).sorted().joined(separator: ",")
    }

    private var grouped: [(EntityKind, [GroupedItem])] {
        let hidden = hiddenKinds
        return canonicalGroups.compactMap { group -> (EntityKind, [GroupedItem])? in
            guard let kind = EntityKind(groupKind: group.kind), !hidden.contains(kind) else { return nil }
            var items: [GroupedItem] = []
            for item in group.items {
                guard let firstClaimId = item.claimIds.first else { continue }
                let firstClaim = claimsById[firstClaimId]
                let primaryContext = (item.description ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                let excerpt = (item.sourceExcerpt ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                let context = !primaryContext.isEmpty
                    ? primaryContext
                    : (!excerpt.isEmpty ? excerpt : (firstClaim?.text ?? item.canonicalName))
                let extraClaims: [GroupedItem.ExtraClaim] = item.claimIds.dropFirst().compactMap { claimId in
                    let claim = claimsById[claimId]
                    return GroupedItem.ExtraClaim(
                        claimId: claimId,
                        context: claim?.text ?? context,
                        sourceDocumentId: claim?.sourceDocumentId ?? item.sourceDocumentId,
                        sourcePageLabel: claim?.sourcePageLabel ?? item.sourcePageLabel,
                        sourceExcerpt: claim?.sourceExcerpt ?? item.sourceExcerpt
                    )
                }
                items.append(GroupedItem(
                    entityId: item.entityId,
                    claimId: firstClaimId,
                    displayName: item.canonicalName,
                    context: context,
                    aliases: item.aliases,
                    confidence: firstClaim?.confidence,
                    sourceDocumentId: item.sourceDocumentId,
                    sourcePageLabel: item.sourcePageLabel,
                    sourceExcerpt: item.sourceExcerpt,
                    extraClaims: extraClaims
                ))
            }
            guard !items.isEmpty else { return nil }
            let sorted = items.sorted { lhs, rhs in
                let leftConfidence = lhs.confidence ?? 0
                let rightConfidence = rhs.confidence ?? 0
                if leftConfidence == rightConfidence {
                    return lhs.displayName.localizedCaseInsensitiveCompare(rhs.displayName) == .orderedAscending
                }
                return leftConfidence > rightConfidence
            }
            return (kind, sorted)
        }
    }

    private var orderedClaimIds: [String] {
        grouped.flatMap { _, items in
            items.flatMap { item in
                [item.claimId] + item.extraClaims.map(\.claimId)
            }
        }
    }

    private var selectedClaims: [Components.Schemas.KnowledgeClaim] {
        orderedClaimIds.compactMap { claimId in
            guard claimSelection.contains(claimId) else { return nil }
            return claimsById[claimId]
        }
    }

    // MARK: - Text digest data

    private struct TextDigestEntry: Identifiable {
        let id: String
        let displayName: String
        let kind: EntityKind
        // Each element is "verb objectPhrase" or bare claim text.
        let svoLines: [String]
    }

    private struct EntityAccumulator {
        let kind: EntityKind
        let displayName: String
        var svoLines: [String]
    }

    private var textDigest: [(EntityKind, [TextDigestEntry])] {
        grouped.map { kind, items in
            let entries = items.map { item in
                let lines = [item.context] + item.extraClaims.map(\.context)
                return TextDigestEntry(
                    id: item.id,
                    displayName: item.displayName,
                    kind: kind,
                    svoLines: lines
                )
            }
            return (kind, entries)
        }
    }

    // MARK: - Text digest view

    @ViewBuilder
    private var textDigestView: some View {
        // Prose digest is always copy-pastable (#3461/#3463). textSelection on
        // the container propagates to every descendant Text; it is safe here
        // (no List row to fight for the click) unlike the selectable rows.
        VStack(alignment: .leading, spacing: 10) {
            if textDigest.isEmpty {
                Text("No knowledge-graph entries for this document yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(textDigest, id: \.0) { kind, entries in
                    VStack(alignment: .leading, spacing: 4) {
                        Label(kind.label.uppercased(), systemImage: kind.systemImage)
                            .font(typeLabelFont)
                            .foregroundStyle(.secondary)

                        ForEach(entries) { entry in
                            let prose = entry.svoLines.joined(separator: "; ")
                            // SwiftUI markdown bold for the entity name.
                            let raw = "**\(entry.displayName)** \(prose)"
                            if let attributed = try? AttributedString(markdown: raw) {
                                Text(attributed)
                                    .font(bodyTextFont)
                                    .fixedSize(horizontal: false, vertical: true)
                            } else {
                                Text(raw)
                                    .font(bodyTextFont)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                }
            }
        }
        .textSelection(.enabled)
    }

    var body: some View {
        // Self-contained: own ScrollView for the digest + a pinned bottom
        // mini-toolbar holding prune / filter / view-mode / refresh and the
        // on-selection claim actions (#3461). The top of the tab is content
        // only; the hosts no longer wrap this in a ScrollView.
        VStack(spacing: 0) {
            if let claimActionMessage {
                Text(claimActionMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal)
                    .padding(.top, 8)
            }
            kgContent
            Divider()
            kgMiniToolbar
        }
        .task(id: documentId) { await loadStatements() }
        // Resync when any claim mutates anywhere — ClaimStore bumps its
        // `changeToken` on each `claim.*` change event fanned from the
        // per-library change-stream (#1862/#1863), retiring the inspector's
        // `.ficheroClaim*` NotificationCenter dependency.
        .onChange(of: claimStore.changeToken) {
            Task { await loadStatements() }
        }
        .alert(
            pendingMergePlan.map {
                "Merge \($0.claimCount) claims into \"\($0.survivorName)\"?"
            } ?? "Merge claims?",
            isPresented: Binding(
                get: { pendingMergePlan != nil },
                set: { if !$0 { pendingMergePlan = nil } }
            ),
            presenting: pendingMergePlan
        ) { plan in
            Button("Merge") {
                Task { await applyMerge(plan) }
            }
            Button("Cancel", role: .cancel) {
                pendingMergePlan = nil
            }
        } message: { plan in
            Text("This keeps \(plan.survivorName) as the canonical claim and folds the others into it.")
        }
        .alert(
            pendingDeleteConfirmation?.title ?? "Delete claim?",
            isPresented: Binding(
                get: { pendingDeleteConfirmation != nil },
                set: { if !$0 { pendingDeleteConfirmation = nil } }
            ),
            presenting: pendingDeleteConfirmation
        ) { pending in
            Button("Delete", role: .destructive) {
                Task { await applyDelete(pending) }
            }
            Button("Cancel", role: .cancel) {
                pendingDeleteConfirmation = nil
            }
        } message: { pending in
            Text(pending.message)
        }
        .alert(
            pendingPruneConfirmation?.title ?? "Prune trivial claims?",
            isPresented: Binding(
                get: { pendingPruneConfirmation != nil },
                set: { if !$0 { pendingPruneConfirmation = nil } }
            ),
            presenting: pendingPruneConfirmation
        ) { pending in
            Button("Prune", role: .destructive) {
                Task { await applyPruneTrivialClaims(scope: pending.scope) }
            }
            Button("Cancel", role: .cancel) {
                pendingPruneConfirmation = nil
            }
        } message: { pending in
            Text(pending.message)
        }
    }

    /// Content region: a native List (keyboard nav + multi-select) in list
    /// mode; a ScrollView for the text digest / loading / empty states.
    @ViewBuilder
    private var kgContent: some View {
        if isLoading {
            ProgressView()
                .padding(.vertical, 8)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let err = loadError {
            Label(err, systemImage: "exclamationmark.triangle")
                .font(.caption)
                .foregroundStyle(.orange)
                .padding()
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        } else if grouped.isEmpty {
            Text("No knowledge-graph entries for this document yet.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding()
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        } else if displayMode == .text {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    textDigestView
                    Divider().padding(.vertical, 4)
                    KGCurationHistorySection(entityService: entityService)
                }
                .padding()
            }
        } else {
            kgClaimList
        }
    }

    /// Native List of claims in per-kind sections (#3425). The List owns
    /// selection, so it provides arrow-key navigation and native multi-select
    /// for free; selecting a single claim focuses/highlights it in Preview.
    /// Keywords (.concept) still render as wrapping lozenges in their section.
    /// Per-kind expand/collapse is deferred (a later enhancement).
    private var kgClaimList: some View {
        List(selection: $claimSelection) {
            ForEach(grouped, id: \.0) { kind, items in
                Section {
                    if kind == .concept {
                        FlowLayout(spacing: 4) {
                            ForEach(items) { item in
                                EntityLozenge(name: item.displayName, entityType: "keywords")
                            }
                        }
                    } else {
                        ForEach(items) { item in
                            kgClaimRow(kind: kind, item: item)
                                .tag(item.claimId)
                        }
                    }
                } header: {
                    Label("\(kind.label) (\(items.count))", systemImage: kind.systemImage)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
            }
            // Curation history stays a trailing section so it scrolls with the
            // claims. Interpretations deliberately stay OUT (AI-integrity: the KG
            // shows ontological facts, never the user's reading as fact) — they
            // render in the Notes tab via DocumentInterpretationsSection (#2470).
            Section {
                KGCurationHistorySection(entityService: entityService)
            }
        }
        .listStyle(.inset)
        .onChange(of: claimSelection) { _, selection in
            focusSingleSelectedClaim(selection)
        }
    }

    private func kgClaimRow(kind: EntityKind, item: GroupedItem) -> some View {
        EntityKindRow(
            item: item,
            kind: kind,
            claimById: claimsById,
            selectedClaimIds: claimSelection,
            claimScopeLabel: documentScopeLabel,
            claimContextMenuTarget: contextMenuTargetClaims(for:),
            onClaimTap: nil,
            applyClaimBulkAction: applyBulkAction,
            requestClaimMergeAction: requestMergeAction(plan:),
            requestClaimDeleteAction: requestDeleteAction(for:),
            requestPruneTrivialAction: requestPruneTrivialAction,
            onNavigateToSource: onNavigateToSource,
            onClaimSelect: onClaimSelect
        )
    }

    /// Focus + highlight the claim when exactly one row is selected — the native
    /// equivalent of the old single-click-focus. Multi-select stays quiet so the
    /// bulk actions operate on the whole set.
    private func focusSingleSelectedClaim(_ selection: Set<String>) {
        guard selection.count == 1,
              let claimId = selection.first,
              let claim = claimsById[claimId] else { return }
        focusClaim(claim)
    }

    private var kgToolbarStatusText: String {
        let count = grouped.reduce(0) { $0 + $1.1.count }
        return "\(count) entit\(count == 1 ? "y" : "ies")"
    }

    /// Pinned bottom mini-toolbar — the single home for the KG tab's controls
    /// (prune / filter / view-mode / refresh) plus the on-selection claim
    /// actions, matching the other inspector panes (#3461).
    private var kgMiniToolbar: some View {
        InspectorBottomMiniToolbar(statusText: kgToolbarStatusText) {
            Menu("Prune trivial") {
                pruneTrivialScopeButtons()
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .disabled(isMutatingClaims)

            kgFilterMenu

            Button {
                displayMode = .text
            } label: {
                Image(systemName: "text.alignleft")
            }
            .buttonStyle(.plain)
            .foregroundStyle(displayMode == .text ? Color.accentColor : Color.secondary)
            .help("Text digest — entities as a dense prose summary, one paragraph per kind")
            .accessibilityLabel("Text digest")

            Button {
                displayMode = .list
            } label: {
                Image(systemName: "list.bullet")
            }
            .buttonStyle(.plain)
            .foregroundStyle(displayMode == .list ? Color.accentColor : Color.secondary)
            .help("List view — entities as grouped, expandable rows you can click through to the source")
            .accessibilityLabel("List view")

            Button {
                Task { await loadStatements() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.plain)
            .help("Reload — re-fetch the knowledge-graph entities for this document")
            .accessibilityLabel("Reload entities")

            if claimSelection.count > 1 {
                claimBulkActionMenu(title: "Approve", systemImage: "checkmark.circle", action: .approve)
                claimBulkActionMenu(title: "Reject", systemImage: "xmark.circle", action: .reject)
                claimBulkActionMenu(title: "Suppress", systemImage: "eye.slash", action: .suppress)
                claimMergeActionMenu(targetClaims: selectedClaims, menuTitle: "Merge")
                deleteActionButton(targetClaims: selectedClaims)
            }
        }
    }

    // Filter Menu — Tinderbox-style "displayed attributes" picker. Each entity
    // kind has its own checkbox; persistence lives in @AppStorage so the choice
    // survives restarts and applies to every doc the user inspects.
    private var kgFilterMenu: some View {
        Menu {
            Section("Scope") {
                Button {
                    includeChildren = false
                } label: {
                    HStack {
                        Text("This item only")
                        Spacer(minLength: 0)
                        if !includeChildren {
                            Image(systemName: "checkmark")
                        }
                    }
                }
                Button {
                    includeChildren = true
                } label: {
                    HStack {
                        Text("Include children")
                        Spacer(minLength: 0)
                        if includeChildren {
                            Image(systemName: "checkmark")
                        }
                    }
                }
            }
            ForEach(EntityKind.displayOrder, id: \.self) { kind in
                let isHidden = hiddenKinds.contains(kind)
                Button {
                    setHidden(kind, hidden: !isHidden)
                } label: {
                    Label(kind.label, systemImage: isHidden ? "" : "checkmark")
                }
            }
            Divider()
            Button("Show all") { hiddenKindsCSV = "" }
            Button("Hide all") {
                hiddenKindsCSV = EntityKind.displayOrder
                    .map(\.rawValue)
                    .sorted()
                    .joined(separator: ",")
            }
        } label: {
            Image(systemName: hiddenKinds.isEmpty
                    ? "line.3.horizontal.decrease.circle"
                    : "line.3.horizontal.decrease.circle.fill")
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Filter — choose which entity kinds (people, places, organizations…) appear in this list")
        .accessibilityLabel("Filter entity kinds")
    }

    private func claimBulkActionMenu(
        title: String,
        systemImage: String,
        action: InspectorClaimBulkAction
    ) -> some View {
        Menu {
            claimBulkScopeButtons(action: action, targetClaims: selectedClaims)
        } label: {
            Label(title, systemImage: systemImage)
        }
        .menuStyle(.borderlessButton)
        .disabled(isMutatingClaims || selectedClaims.isEmpty)
    }

    private func claimMergeActionMenu(
        targetClaims: [Components.Schemas.KnowledgeClaim],
        menuTitle: String
    ) -> some View {
        // One destination choice per candidate so the user picks which claim
        // the others fold INTO (#2499). Heuristic survivor marked Recommended.
        let recommendedId = InspectorClaimBulkSelection.mergeSurvivor(in: targetClaims)?.id
        let canMerge = InspectorClaimBulkSelection.mergePlan(for: targetClaims) != nil
        return Menu {
            if canMerge {
                ForEach(targetClaims.filter { $0.id != nil }, id: \.id) { claim in
                    if let id = claim.id,
                       let plan = InspectorClaimBulkSelection.mergePlan(
                            for: targetClaims, survivorId: id) {
                        Button(mergeDestinationLabel(
                            name: claim.displayMergeName,
                            isRecommended: id == recommendedId
                        )) {
                            pendingMergePlan = plan
                        }
                    }
                }
            } else {
                Button("Requires 2+ live claims") {}
                    .disabled(true)
            }
        } label: {
            Label(menuTitle, systemImage: "arrow.triangle.merge")
        }
        .menuStyle(.borderlessButton)
        .disabled(isMutatingClaims || !canMerge)
    }

    /// Menu-button title for a merge destination (#2499). Marks the heuristic
    /// survivor as "(Recommended)" so the sensible default is one click away.
    private func mergeDestinationLabel(name: String, isRecommended: Bool) -> String {
        isRecommended ? "Into \"\(name)\" (Recommended)" : "Into \"\(name)\""
    }

    private func deleteActionButton(
        targetClaims: [Components.Schemas.KnowledgeClaim]
    ) -> some View {
        Button(role: .destructive) {
            requestDeleteAction(for: targetClaims)
        } label: {
            Label("Delete", systemImage: "trash")
        }
        .buttonStyle(.borderless)
        .disabled(isMutatingClaims || targetClaims.isEmpty)
    }

    @ViewBuilder
    private func claimBulkScopeButtons(
        action: InspectorClaimBulkAction,
        targetClaims: [Components.Schemas.KnowledgeClaim]
    ) -> some View {
        Button(documentScopeLabel) {
            Task {
                await applyBulkAction(
                    action,
                    scope: .pageOrFolderOnly,
                    targetClaims: targetClaims
                )
            }
        }
        Button("Library-wide") {
            Task {
                await applyBulkAction(
                    action,
                    scope: .libraryWide,
                    targetClaims: targetClaims
                )
            }
        }
    }

    @ViewBuilder
    private func pruneTrivialScopeButtons() -> some View {
        Button(documentScopeLabel) {
            requestPruneTrivialAction(.pageOrFolderOnly)
        }
        Button("Library-wide") {
            requestPruneTrivialAction(.libraryWide)
        }
    }

    private func contextMenuTargetClaims(
        for claim: Components.Schemas.KnowledgeClaim
    ) -> [Components.Schemas.KnowledgeClaim] {
        guard let claimId = claim.id else { return [claim] }
        if claimSelection.contains(claimId) {
            return selectedClaims
        }
        return [claim]
    }

    private func requestDeleteAction(for targetClaims: [Components.Schemas.KnowledgeClaim]) {
        pendingDeleteConfirmation = PendingClaimDeleteConfirmation(claims: targetClaims)
    }

    // The old modifier-key selection reducer (handleClaimTap) was retired with
    // the native-List conversion (#3425): List(selection:) owns single-click,
    // cmd/shift multi-select, and arrow-key navigation. Focus now flows from
    // focusSingleSelectedClaim on selection change.

    private func focusClaim(_ claim: Components.Schemas.KnowledgeClaim) {
        guard let claimId = claim.id else { return }
        kgFocusState.focusClaim(
            claimId: claimId,
            entityId: claim.subjectEntityId,
            sourceDocumentId: claim.sourceDocumentId,
            sourcePageLabel: claim.sourcePageLabel
        )
        onClaimSelect?(
            claimId,
            claim.sourceExcerpt,
            claim.sourceDocumentId,
            claim.sourcePageLabel,
            nil,
            nil
        )
    }

    private func loadStatements() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }

        do {
            let response = try await entityService.documentKnowledgeGraph(
                documentId: documentId,
                includeChildren: includeChildren
            )
            claims = response.claims
            canonicalGroups = response.groups
            syncSelectionToLoadedClaims()
        } catch is CancellationError {
            // Task superseded by a newer page selection — not a load failure.
        } catch {
            loadError = "Couldn't load: \(error.localizedDescription)"
            claims = []
            canonicalGroups = []
            claimSelection = []
            claimSelectionAnchor = nil
        }
    }

    private func syncSelectionToLoadedClaims() {
        let validIds = Set(orderedClaimIds)
        claimSelection = claimSelection.intersection(validIds)
        if let claimSelectionAnchor, !validIds.contains(claimSelectionAnchor) {
            self.claimSelectionAnchor = nil
        }
    }

    private func applyBulkAction(
        _ action: InspectorClaimBulkAction,
        scope: InspectorEntityBulkActionScope,
        targetClaims: [Components.Schemas.KnowledgeClaim]
    ) async {
        let claimIds = targetClaims.compactMap(\.id)
        let missingIdCount = targetClaims.count - claimIds.count
        guard !claimIds.isEmpty || (action == .suppress && scope == .libraryWide) else {
            claimActionMessage = "Selected claims are missing IDs, so \(action.verb.lowercased()) was skipped."
            return
        }

        isApplyingBulkAction = true
        claimActionMessage = nil
        defer { isApplyingBulkAction = false }

        do {
            let suppressRules = action == .suppress && scope == .libraryWide
                ? InspectorClaimBulkSelection.libraryWideSuppressRules(for: targetClaims)
                : []

            if !claimIds.isEmpty {
                _ = try await kgCurationService.batchSetClaimCurationState(
                    claimIds: claimIds,
                    curationState: action.curationState
                )
            }

            if action == .suppress, scope == .libraryWide, !suppressRules.isEmpty {
                _ = try await kgCurationService.batchCreateClaimRules(suppressRules)
            }

            await loadStatements()
            claimSelection = []
            claimSelectionAnchor = nil

            if claimIds.isEmpty && suppressRules.isEmpty {
                // Nothing was actually applied — don't report a false success.
                claimActionMessage = missingIdCount > 0
                    ? "Selected claims are missing IDs, so \(action.verb.lowercased()) was skipped."
                    : "Nothing to \(action.verb.lowercased())."
            } else {
                var message = "\(action.verb) \(claimIds.count) claim"
                message += claimIds.count == 1 ? "" : "s"
                if action == .suppress, scope == .libraryWide {
                    message += " and wrote \(suppressRules.count) suppress rule"
                    message += suppressRules.count == 1 ? "" : "s"
                }
                if missingIdCount > 0 {
                    message += "; skipped \(missingIdCount) without IDs"
                }
                claimActionMessage = message
            }
        } catch {
            claimActionMessage = "Couldn't \(action.verb.lowercased()) claims: \(error.localizedDescription)"
        }
    }

    private func requestMergeAction(plan: InspectorClaimBulkSelection.MergePlan) {
        pendingMergePlan = plan
    }

    private func applyDelete(_ pending: PendingClaimDeleteConfirmation) async {
        let claimIds = pending.claims.compactMap(\.id)
        let missingIdCount = pending.claims.count - claimIds.count
        guard !claimIds.isEmpty else {
            claimActionMessage = "Selected claims are missing IDs, so delete was skipped."
            pendingDeleteConfirmation = nil
            return
        }

        isApplyingBulkAction = true
        claimActionMessage = nil
        pendingDeleteConfirmation = nil
        defer { isApplyingBulkAction = false }

        do {
            for claimId in claimIds {
                try await entityService.deleteClaim(claimId)
            }
            await loadStatements()
            claimSelection = []
            claimSelectionAnchor = nil

            var message = "Deleted \(claimIds.count) claim"
            message += claimIds.count == 1 ? "" : "s"
            if missingIdCount > 0 {
                message += "; skipped \(missingIdCount) without IDs"
            }
            claimActionMessage = message
        } catch {
            inspectorClaimsLogger.error(
                "Claim delete failed for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
            claimActionMessage = "Couldn't delete claims: \(error.localizedDescription)"
        }
    }

    // swiftlint:disable:next todo
    // TODO(#1689): claim unmerge UI
    private func applyMerge(_ plan: InspectorClaimBulkSelection.MergePlan) async {
        isApplyingBulkAction = true
        claimActionMessage = nil
        pendingMergePlan = nil
        defer { isApplyingBulkAction = false }

        do {
            _ = try await kgCurationService.mergeClaims(
                survivorId: plan.survivorId,
                absorbedIds: plan.absorbedClaimIds
            )
            await loadStatements()
            claimSelection = []
            claimSelectionAnchor = nil
            claimActionMessage = "Merged \(plan.claimCount) claims."
        } catch {
            inspectorClaimsLogger.error(
                "Claim merge failed for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
            claimActionMessage = "Couldn't merge claims: \(error.localizedDescription)"
        }
    }

    private func requestPruneTrivialAction(_ scope: InspectorEntityBulkActionScope) {
        pendingPruneConfirmation = PendingPruneConfirmation(
            scope: pruneScope(for: scope),
            title: pruneConfirmationTitle(for: scope),
            message: pruneConfirmationMessage(for: scope)
        )
    }

    private func pruneScope(
        for scope: InspectorEntityBulkActionScope
    ) -> KGCurationServiceGenerated.PruneTrivialScope {
        switch scope {
        case .pageOrFolderOnly:
            return documentScope.pruneScope(documentId: documentId)
        case .libraryWide:
            return .libraryWide
        }
    }

    private func pruneConfirmationTitle(for scope: InspectorEntityBulkActionScope) -> String {
        switch scope {
        case .pageOrFolderOnly:
            return "Prune trivially-true claims in \(documentScope.confirmationTarget)?"
        case .libraryWide:
            return "Prune trivially-true claims across the whole library?"
        }
    }

    private func pruneConfirmationMessage(for scope: InspectorEntityBulkActionScope) -> String {
        switch scope {
        case .pageOrFolderOnly:
            return "This updates claim curation state for the current scope and refreshes the inspector list."
        case .libraryWide:
            return "This scans the whole library, updates matching claims, and may write a persistent suppress is-a copulas rule."
        }
    }

    private func applyPruneTrivialClaims(
        scope: KGCurationServiceGenerated.PruneTrivialScope
    ) async {
        isPruningTrivialClaims = true
        claimActionMessage = nil
        defer {
            isPruningTrivialClaims = false
            pendingPruneConfirmation = nil
        }

        do {
            let response = try await kgCurationService.pruneTrivialClaims(scope: scope)
            await loadStatements()
            claimSelection = []
            claimSelectionAnchor = nil

            var message = "Pruned \(response.suppressedCount) trivial claim"
            if response.suppressedCount != 1 {
                message += "s"
            }
            claimActionMessage = message
        } catch {
            claimActionMessage = "Couldn't prune trivial claims: \(error.localizedDescription)"
        }
    }
}

// MARK: - KnowledgeGraphInspectorSection utilities

extension KnowledgeGraphInspectorSection {
    static let groupVisibleCap = 10

    static func visibleItems<T>(_ items: [T], showingAll: Bool, cap: Int = groupVisibleCap) -> [T] {
        if showingAll || items.count <= cap { return items }
        return Array(items.prefix(cap))
    }

    static func showAllButtonTitle(itemCount: Int, showingAll: Bool, cap: Int = groupVisibleCap) -> String? {
        guard itemCount > cap else { return nil }
        return showingAll ? "Show less" : "Show all (\(itemCount))"
    }

    static func isKindStored(_ kind: EntityKind, in csv: String) -> Bool {
        csv.split(separator: ",").contains(Substring(kind.rawValue))
    }
}

enum InspectorClaimDocumentScope {
    case page
    case folder

    var label: String {
        switch self {
        case .page:
            return "This page only"
        case .folder:
            return "This folder only"
        }
    }

    var confirmationTarget: String {
        switch self {
        case .page:
            return "this page"
        case .folder:
            return "this folder"
        }
    }

    func pruneScope(documentId: String) -> KGCurationServiceGenerated.PruneTrivialScope {
        switch self {
        case .page:
            return .document(documentId: documentId)
        case .folder:
            return .folder(folderId: documentId)
        }
    }
}

struct PendingPruneConfirmation: Identifiable {
    let id = UUID()
    let scope: KGCurationServiceGenerated.PruneTrivialScope
    let title: String
    let message: String
}

struct PendingClaimDeleteConfirmation: Identifiable {
    let claims: [Components.Schemas.KnowledgeClaim]

    var id: String {
        claims.compactMap(\.id).sorted().joined(separator: "|")
    }

    var title: String {
        if claims.count == 1, let claim = claims.first {
            return "Delete \"\(claim.displayMergeName)\"?"
        }
        return "Delete \(claims.count) claims?"
    }

    var message: String {
        if claims.count == 1 {
            return "This removes the claim from the knowledge graph. Related entities stay in place."
        }
        return "This removes the selected claims from the knowledge graph. Related entities stay in place."
    }
}

enum InspectorClaimBulkAction: Equatable {
    case approve
    case reject
    case suppress

    var verb: String {
        switch self {
        case .approve: return "Approved"
        case .reject: return "Rejected"
        case .suppress: return "Suppressed"
        }
    }

    var curationState: Components.Schemas.ClaimCurationState {
        switch self {
        case .approve: return .curated
        case .reject, .suppress: return .rejected
        }
    }
}

struct InspectorClaimBulkSelection {
    struct MergePlan: Equatable, Identifiable {
        let survivorId: String
        let absorbedClaimIds: [String]
        let survivorName: String
        let claimCount: Int

        var id: String {
            "\(survivorId):\(absorbedClaimIds.sorted().joined(separator: ","))"
        }
    }

    static func libraryWideSuppressRules(
        for claims: [Components.Schemas.KnowledgeClaim]
    ) -> [Components.Schemas.ClaimRuleCreateRequest] {
        var seen = Set<String>()
        return claims.compactMap { claim in
            let subject = claim.subjectCanonical?.trimmingCharacters(in: .whitespacesAndNewlines)
            let predicate = claim.predicateVerb?.trimmingCharacters(in: .whitespacesAndNewlines)
            let object = claim.objectPhrase?.trimmingCharacters(in: .whitespacesAndNewlines)
            let normalizedSubject = (subject?.isEmpty == false) ? subject : nil
            let normalizedPredicate = (predicate?.isEmpty == false) ? predicate : nil
            let normalizedObject = (object?.isEmpty == false) ? object : nil
            guard normalizedSubject != nil || normalizedPredicate != nil || normalizedObject != nil else {
                return nil
            }

            let dedupeKey = [
                normalizedSubject?.lowercased() ?? "",
                normalizedPredicate?.lowercased() ?? "",
                normalizedObject?.lowercased() ?? ""
            ].joined(separator: "|")
            guard seen.insert(dedupeKey).inserted else { return nil }

            // Follow-up (#1763): prune-trivial when the selection is entirely is-a/copula claims.
            return Components.Schemas.ClaimRuleCreateRequest(
                action: .disable,
                matchPredicateVerb: normalizedPredicate,
                matchSubjectName: normalizedSubject,
                matchObjectPhrase: normalizedObject,
                suppressIsACopulas: false,
                reason: "Bulk suppress from inspector",
                createdBy: "human"
            )
        }
    }

    /// Merge plan using the heuristic survivor (`mergeSurvivor`) as the
    /// destination — the default/recommended choice.
    static func mergePlan(
        for claims: [Components.Schemas.KnowledgeClaim]
    ) -> MergePlan? {
        guard let survivorId = mergeSurvivor(in: claims)?.id else { return nil }
        return mergePlan(for: claims, survivorId: survivorId)
    }

    /// Merge plan with a caller-chosen survivor so the user can pick which
    /// claim is the merge DESTINATION (#2499). `survivorId` must be one of
    /// `claims`; the rest fold into it. Same validity gates as the heuristic
    /// path (2+ claims, none already merged, all have IDs).
    static func mergePlan(
        for claims: [Components.Schemas.KnowledgeClaim],
        survivorId: String
    ) -> MergePlan? {
        guard claims.count > 1,
              claims.allSatisfy({ $0.mergedIntoId == nil }),
              let survivor = claims.first(where: { $0.id == survivorId })
        else {
            return nil
        }

        let claimIds = claims.compactMap(\.id)
        guard claimIds.count == claims.count else { return nil }

        let absorbedClaimIds = claimIds.filter { $0 != survivorId }
        guard !absorbedClaimIds.isEmpty else { return nil }

        return MergePlan(
            survivorId: survivorId,
            absorbedClaimIds: absorbedClaimIds,
            survivorName: survivor.displayMergeName,
            claimCount: claims.count
        )
    }

    static func mergeSurvivor(
        in claims: [Components.Schemas.KnowledgeClaim]
    ) -> Components.Schemas.KnowledgeClaim? {
        claims.sorted { lhs, rhs in
            let lhsCorroboration = lhs.corroborationCount ?? 0
            let rhsCorroboration = rhs.corroborationCount ?? 0
            if lhsCorroboration != rhsCorroboration {
                return lhsCorroboration > rhsCorroboration
            }

            let lhsWeighted = lhs.weightedCorroborationCount ?? 0
            let rhsWeighted = rhs.weightedCorroborationCount ?? 0
            if lhsWeighted != rhsWeighted {
                return lhsWeighted > rhsWeighted
            }

            let lhsSupport = lhs.sourceSupports?.count ?? 0
            let rhsSupport = rhs.sourceSupports?.count ?? 0
            if lhsSupport != rhsSupport {
                return lhsSupport > rhsSupport
            }

            let lhsName = lhs.displayMergeName
            let rhsName = rhs.displayMergeName
            if lhsName.count != rhsName.count {
                return lhsName.count > rhsName.count
            }

            let lexical = lhsName.localizedCaseInsensitiveCompare(rhsName)
            if lexical != .orderedSame {
                return lexical == .orderedAscending
            }
            return (lhs.id ?? "") < (rhs.id ?? "")
        }.first
    }
}

extension Components.Schemas.KnowledgeClaim {
    var displayMergeName: String {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if !text.isEmpty {
            return text
        }

        let pieces = [subjectCanonical, predicateVerb, objectPhrase]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        if !pieces.isEmpty {
            return pieces.joined(separator: " ")
        }

        return id ?? "Untitled claim"
    }
}
// swiftlint:enable file_length
