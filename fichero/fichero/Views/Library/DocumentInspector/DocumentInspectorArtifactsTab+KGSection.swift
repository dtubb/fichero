import AppKit
import FicheroAPIClient
import SwiftUI

// swiftlint:disable file_length

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
    let documentScopeLabel: String
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
    @StateObject private var loadState = KnowledgeGraphInspectorLoadState()
    @State private var claimSelection: Set<String> = []
    @State private var claimSelectionAnchor: String?
    @State private var isApplyingBulkAction = false
    @State private var claimActionMessage: String?
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

    private struct TextDigestEntry {
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
                return TextDigestEntry(displayName: item.displayName, kind: kind, svoLines: lines)
            }
            return (kind, entries)
        }
    }

    // MARK: - Text digest view

    @ViewBuilder
    private var textDigestView: some View {
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

                        ForEach(entries, id: \.displayName) { entry in
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
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader
            if claimSelection.count > 1 {
                claimBulkActionBar
            }
            if let claimActionMessage {
                Text(claimActionMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if isLoading {
                ProgressView().padding(.vertical, 8)
            } else if let err = loadError {
                Label(err, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.orange)
            } else if grouped.isEmpty {
                Text("No knowledge-graph entries for this document yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else if displayMode == .text {
                textDigestView
            } else {
                ForEach(grouped, id: \.0) { kind, items in
                    EntityKindBlock(
                        kind: kind,
                        items: items,
                        claimById: claimsById,
                        selectedClaimIds: claimSelection,
                        claimScopeLabel: documentScopeLabel,
                        claimContextMenuTarget: contextMenuTargetClaims(for:),
                        onClaimTap: handleClaimTap(_:),
                        applyClaimBulkAction: applyBulkAction,
                        onNavigateToSource: onNavigateToSource,
                        onClaimSelect: onClaimSelect
                    )
                }
            }

            Divider()
                .padding(.vertical, 4)
            KGCurationHistorySection(entityService: entityService)
            Divider()
                .padding(.vertical, 4)
            DocumentInterpretationsSection(
                documentId: documentId,
                entityService: entityService
            )
        }
        .task(id: documentId) { await loadStatements() }
    }

    private var claimBulkActionBar: some View {
        HStack(spacing: 8) {
            Text("\(claimSelection.count) selected")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            claimBulkActionMenu(title: "Approve", systemImage: "checkmark.circle", action: .approve)
            claimBulkActionMenu(title: "Reject", systemImage: "xmark.circle", action: .reject)
            claimBulkActionMenu(title: "Suppress", systemImage: "eye.slash", action: .suppress)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.secondary.opacity(0.08))
        )
    }

    private var sectionHeader: some View {
        // No "Knowledge Graph" title/icon — the inspector tab already names
        // this surface, so the in-pane label was redundant (#1244). The header
        // is now just the filter + view-mode + reload controls, right-aligned.
        HStack(spacing: 8) {
            Spacer()
            // Filter Menu — Tinderbox-style "displayed attributes" picker.
            // Each entity kind has its own checkbox; persistence lives in
            // @AppStorage so the choice survives restarts and applies to
            // every doc the user inspects.
            Menu {
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
            // Text / List mode toggle
            Button {
                displayMode = .text
            } label: {
                Image(systemName: "text.alignleft")
            }
            .buttonStyle(.plain)
            .foregroundStyle(displayMode == .text ? Color.accentColor : Color.secondary)
            .help("Text digest — entities as a dense prose summary, one paragraph per kind")
            Button {
                displayMode = .list
            } label: {
                Image(systemName: "list.bullet")
            }
            .buttonStyle(.plain)
            .foregroundStyle(displayMode == .list ? Color.accentColor : Color.secondary)
            .help("List view — entities as grouped, expandable rows you can click through to the source")
            Button {
                Task { await loadStatements() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.plain)
            .help("Reload — re-fetch the knowledge-graph entities for this document")
        }
        .foregroundStyle(.primary)
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
        .disabled(isApplyingBulkAction || selectedClaims.isEmpty)
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

    private func contextMenuTargetClaims(
        for claim: Components.Schemas.KnowledgeClaim
    ) -> [Components.Schemas.KnowledgeClaim] {
        guard let claimId = claim.id else { return [claim] }
        if claimSelection.contains(claimId) {
            return selectedClaims
        }
        return [claim]
    }

    private func handleClaimTap(_ claim: Components.Schemas.KnowledgeClaim) {
        guard let claimId = claim.id else {
            focusClaim(claim)
            return
        }

        let modifiers = InspectorEntitySelectionModifiers(nsEventFlags: NSEvent.modifierFlags)
        let reduced = InspectorEntityBulkSelection.reduceTap(
            tappedId: claimId,
            orderedIds: orderedClaimIds,
            selection: claimSelection,
            anchor: claimSelectionAnchor,
            modifiers: modifiers
        )
        claimSelection = reduced.selection
        claimSelectionAnchor = reduced.anchor

        guard modifiers.isEmpty else { return }
        focusClaim(claim)
    }

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
                includeChildren: true
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
}
// swiftlint:enable file_length
