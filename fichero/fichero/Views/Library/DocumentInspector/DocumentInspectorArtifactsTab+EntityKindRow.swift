import FicheroAPIClient
import SwiftUI

// swiftlint:disable file_length type_body_length

// MARK: - EntityKindRow

/// One row inside an EntityKindBlock. The **name** is tappable —
/// clicking fires a scoped entity search (e.g. `person:"…"`) via the
/// typed `EntitySearchState` request, same path Keyword
/// lozenges use. Aliases / page reference / context render as plain
/// selectable text below for ⌘C. (#882)
struct EntityKindRow: View {
    let item: GroupedItem
    let kind: EntityKind
    var claimById: [String: Components.Schemas.KnowledgeClaim] = [:]
    var selectedClaimIds: Set<String> = []
    var claimScopeLabel: String?
    var claimContextMenuTarget: ((Components.Schemas.KnowledgeClaim) -> [Components.Schemas.KnowledgeClaim])?
    var onClaimTap: ((Components.Schemas.KnowledgeClaim) -> Void)?
    var applyClaimBulkAction: ((
        InspectorClaimBulkAction,
        InspectorEntityBulkActionScope,
        [Components.Schemas.KnowledgeClaim]
    ) async -> Void)?
    // Takes the caller-chosen merge plan (survivor picked in the menu) so the
    // user controls the merge destination (#2499).
    var requestClaimMergeAction: ((InspectorClaimBulkSelection.MergePlan) -> Void)?
    var requestClaimDeleteAction: (([Components.Schemas.KnowledgeClaim]) -> Void)?
    var requestPruneTrivialAction: ((InspectorEntityBulkActionScope) -> Void)?
    var onNavigateToSource: ((String) -> Void)?
    var onClaimSelect: ((String, String?, String?, String?, Int?, Int?) -> Void)?

    @Environment(ClaimFocusState.self) private var claimFocusState
    @Environment(KGFocusState.self) private var kgFocusState
    @AppStorage("editor.fontSize") private var defaultFontSize: Double = 13
    @State private var claimForEditing: Components.Schemas.KnowledgeClaim?
    @State private var rowError: String?

    private var bodyTextFont: Font {
        .system(size: CGFloat(defaultFontSize))
    }

    private var secondaryTextFont: Font {
        .system(size: CGFloat(max(defaultFontSize - 1, 10)))
    }

    private var primaryClaim: Components.Schemas.KnowledgeClaim? {
        claimById[item.claimId]
    }

    var body: some View {
        // Layout:
        //   line 1: [name button]  (aka alias1, alias2)  (p. label)   → arrow  [select claim]
        //   line 2: context  (when non-empty, non-redundant)
        // Name is its own Button so a tap doesn't have to compete with
        // textSelection on the rest of the row.
        VStack(alignment: .leading, spacing: 0) {
            claimBlock(
                claimId: item.claimId,
                context: item.context,
                sourceDocumentId: item.sourceDocumentId,
                sourcePageLabel: item.sourcePageLabel,
                sourceExcerpt: item.sourceExcerpt,
                confidence: item.confidence,
                isPrimary: true
            )

            // Additional SVO claims for the same entity (#1109).
            // Each renders as an indented context + excerpt pair, visually
            // subordinate to the primary claim above.
            if !item.extraClaims.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(item.extraClaims, id: \.claimId) { extra in
                        claimBlock(
                            claimId: extra.claimId,
                            context: extra.context,
                            sourceDocumentId: extra.sourceDocumentId,
                            sourcePageLabel: extra.sourcePageLabel,
                            sourceExcerpt: extra.sourceExcerpt,
                            confidence: claimById[extra.claimId]?.confidence,
                            isPrimary: false
                        )
                    }
                }
                .padding(.leading, 8)
            }

            if let rowError {
                Text(rowError)
                    .font(.caption2)
                    .foregroundStyle(.red)
            }
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
        .sheet(isPresented: Binding(
            get: { claimForEditing != nil },
            set: { if !$0 { claimForEditing = nil } }
        )) {
            if let claimForEditing {
                // EditClaimSheet persists via PATCH; the backend emits
                // `claim.updated`, the change-stream bumps ClaimStore.changeToken,
                // and the KG section resyncs — no NotificationCenter nudge (#1862).
                EditClaimSheet(claim: claimForEditing) { _ in
                    self.claimForEditing = nil
                }
            }
        }
    }

    private func focusPrimaryClaim() {
        if let primaryClaim {
            handleClaimTap(primaryClaim)
            return
        }
        kgFocusState.focusClaim(
            claimId: item.claimId,
            entityId: item.entityId,
            sourceDocumentId: item.sourceDocumentId,
            sourcePageLabel: item.sourcePageLabel
        )
    }

    /// Aliases + page reference rendered as one selectable text run,
    /// sitting beside the tappable name on line 1.
    private var trailingText: Text {
        let aliasesText = item.aliases.isEmpty ? "" : " (aka \(item.aliases.joined(separator: ", ")))"
        let pageRefText = pageReference.map { "  (\($0))" } ?? ""
        if !item.aliases.isEmpty {
            return Text("\(aliasesText)\(pageRefText)")
                .font(secondaryTextFont)
                .foregroundStyle(.secondary)
        }
        return Text(pageRefText)
            .font(secondaryTextFont)
            .foregroundStyle(.secondary)
    }

    /// Scholarly-style page reference: prefer the recorded label
    /// (e.g. "page 4", "folio 12r"); strip a leading "page " so we can
    /// abbreviate it to "p. 4". Returns nil when no label is available
    /// (don't fabricate a reference from nothing).
    private var pageReference: String? {
        guard let raw = item.sourcePageLabel?.trimmingCharacters(in: .whitespaces),
              !raw.isEmpty
        else { return nil }
        let lower = raw.lowercased()
        if lower.hasPrefix("page "), let numericPart = lower.split(separator: " ").last {
            return "p. \(numericPart)"
        }
        return raw
    }

    private func loadClaimForEditing() {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        rowError = nil
        Task {
            do {
                claimForEditing = try await library.entityService.getClaim(item.claimId)
            } catch {
                rowError = error.localizedDescription
            }
        }
    }

    // swiftlint:disable function_body_length cyclomatic_complexity function_parameter_count
    @ViewBuilder
    private func claimBlock(
        claimId: String,
        context: String,
        sourceDocumentId: String?,
        sourcePageLabel: String?,
        sourceExcerpt: String?,
        confidence: Double?,
        isPrimary: Bool
    ) -> some View {
        let claim = claimById[claimId]
        let isSelected = selectedClaimIds.contains(claimId)
        let isFocused = claimFocusState.isClaimSelected(claimId)

        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                if isPrimary {
                    Button(action: {
                        if let claim {
                            handleClaimTap(claim)
                        } else {
                            focusPrimaryClaim()
                        }
                    }, label: {
                        Text(item.displayName)
                            .font(bodyTextFont)
                            .fontWeight(.medium)
                            .foregroundStyle(isFocused ? Color.accentColor : Color.primary)
                    })
                    .buttonStyle(.plain)
                    .help("Focus \"\(item.displayName)\"")
                    .accessibilityHint("Focuses this \(kind.label.lowercased())")

                    trailingText
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .textSelection(.enabled)
                } else {
                    Text("Related claim")
                        .font(secondaryTextFont)
                        .foregroundStyle(.secondary)
                }

                if let curationState = claim?.curationState, curationState != .unreviewed {
                    ClaimCurationBadge(state: curationState)
                }

                if let confidence {
                    Text(String(format: "%.2f", confidence))
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.secondary.opacity(0.12))
                        .clipShape(Capsule())
                        .help("Claim confidence")
                }
                if isPrimary, item.includesChildren {
                    Text("Includes children")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.secondary.opacity(0.12))
                        .clipShape(Capsule())
                        .help("This row includes claims from child documents")
                }

                if isPrimary, let onClaimSelect = onClaimSelect {
                    Button(action: {
                        if let claim {
                            handleClaimTap(claim)
                        } else {
                            focusPrimaryClaim()
                            onClaimSelect(
                                claimId,
                                sourceExcerpt,
                                sourceDocumentId,
                                sourcePageLabel,
                                nil,
                                nil
                            )
                        }
                    }, label: {
                        Image(systemName: isFocused ? "star.fill" : "star")
                            .font(.system(size: 12))
                            .foregroundStyle(isFocused ? Color.accentColor : Color.secondary)
                    })
                    .buttonStyle(.plain)
                    .help(isFocused ? "Claim selected for highlighting" : "Select claim for highlighting")
                }

                if isPrimary,
                   let sourceDocumentId,
                   let navigate = onNavigateToSource {
                    Button {
                        navigate(sourceDocumentId)
                    } label: {
                        Image(systemName: "arrow.right.circle")
                            .font(.body)
                            .foregroundStyle(Color.accentColor)
                    }
                    .buttonStyle(.plain)
                    .help("Go to source")
                }
            }

            if !context.isEmpty,
               context != item.displayName,
               !item.displayName.contains(context) {
                Text(context)
                    .font(bodyTextFont)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }

            if let excerpt = sourceExcerpt,
               !excerpt.isEmpty,
               excerpt != context,
               excerpt != item.displayName {
                Button {
                    EntitySearchState.shared.request(name: excerpt, entityType: nil)
                } label: {
                    Text("\u{201C}\(excerpt)\u{201D}")
                        .font(secondaryTextFont)
                        .italic()
                        .foregroundStyle(.secondary)
                        .lineLimit(3)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                .help("Search the library for this quote")
            }
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 4)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(isSelected ? Color.accentColor.opacity(0.16) : Color.clear)
        )
        .contentShape(Rectangle())
        .onTapGesture {
            if let claim {
                handleClaimTap(claim)
            }
        }
        // Single-click selects (above); double-click opens — focus the
        // claim and jump to its source page, Finder-style. Matches the
        // Entities-tab interaction. (#1864/#1865)
        .simultaneousGesture(
            TapGesture(count: 2).onEnded {
                openClaim(claimId: claimId, sourceDocumentId: sourceDocumentId)
            }
        )
        .contextMenu {
            if let claim {
                claimBulkContextMenu(for: claim)
                if isPrimary {
                    Divider()
                }
            }
            if isPrimary {
                Button("Edit claim…") {
                    loadClaimForEditing()
                }
            }
        }
    }
    // swiftlint:enable function_body_length cyclomatic_complexity function_parameter_count

    private func handleClaimTap(_ claim: Components.Schemas.KnowledgeClaim) {
        if let onClaimTap {
            onClaimTap(claim)
            return
        }
        kgFocusState.focusClaim(
            claimId: claim.id,
            entityId: claim.subjectEntityId ?? item.entityId,
            sourceDocumentId: claim.sourceDocumentId ?? item.sourceDocumentId,
            sourcePageLabel: claim.sourcePageLabel ?? item.sourcePageLabel
        )
    }

    /// Double-click "open": focus the claim and navigate the reading view
    /// to its source document/page when a source is known. (#1864)
    private func openClaim(claimId: String, sourceDocumentId: String?) {
        if let claim = claimById[claimId] {
            handleClaimTap(claim)
        } else {
            focusPrimaryClaim()
        }
        if let sourceDocumentId, let onNavigateToSource {
            onNavigateToSource(sourceDocumentId)
        }
    }

    // swiftlint:disable function_body_length
    @ViewBuilder
    private func claimBulkContextMenu(
        for claim: Components.Schemas.KnowledgeClaim
    ) -> some View {
        if let claimContextMenuTarget {
            let targetClaims = claimContextMenuTarget(claim)
            if let requestClaimMergeAction {
                if InspectorClaimBulkSelection.mergePlan(for: targetClaims) != nil {
                    let recommendedId = InspectorClaimBulkSelection.mergeSurvivor(in: targetClaims)?.id
                    Menu("Merge") {
                        // One destination per candidate — user picks the survivor (#2499).
                        ForEach(targetClaims.filter { $0.id != nil }, id: \.id) { candidate in
                            if let id = candidate.id,
                               let plan = InspectorClaimBulkSelection.mergePlan(
                                    for: targetClaims, survivorId: id) {
                                Button(id == recommendedId
                                    ? "Into \"\(candidate.displayMergeName)\" (Recommended)"
                                    : "Into \"\(candidate.displayMergeName)\"") {
                                    requestClaimMergeAction(plan)
                                }
                            }
                        }
                    }
                } else {
                    Button("Merge requires 2+ live claims") {}
                        .disabled(true)
                }
            }
        }
        if let claimScopeLabel, let claimContextMenuTarget, let applyClaimBulkAction {
            let targetClaims = claimContextMenuTarget(claim)
            Menu("Approve") {
                claimBulkScopeButtons(
                    scopeLabel: claimScopeLabel,
                    action: .approve,
                    targetClaims: targetClaims,
                    applyClaimBulkAction: applyClaimBulkAction
                )
            }
            Menu("Reject") {
                claimBulkScopeButtons(
                    scopeLabel: claimScopeLabel,
                    action: .reject,
                    targetClaims: targetClaims,
                    applyClaimBulkAction: applyClaimBulkAction
                )
            }
            Menu("Suppress") {
                claimBulkScopeButtons(
                    scopeLabel: claimScopeLabel,
                    action: .suppress,
                    targetClaims: targetClaims,
                    applyClaimBulkAction: applyClaimBulkAction
                )
            }
            if let requestPruneTrivialAction {
                Menu("Prune trivial") {
                    Button(claimScopeLabel) {
                        requestPruneTrivialAction(.pageOrFolderOnly)
                    }
                    Button("Library-wide") {
                        requestPruneTrivialAction(.libraryWide)
                    }
                }
            }
            if let requestClaimDeleteAction {
                Button("Delete…", role: .destructive) {
                    requestClaimDeleteAction(targetClaims)
                }
            }
        }
    }
    // swiftlint:enable function_body_length

    @ViewBuilder
    private func claimBulkScopeButtons(
        scopeLabel: String,
        action: InspectorClaimBulkAction,
        targetClaims: [Components.Schemas.KnowledgeClaim],
        applyClaimBulkAction: @escaping (
            InspectorClaimBulkAction,
            InspectorEntityBulkActionScope,
            [Components.Schemas.KnowledgeClaim]
        ) async -> Void
    ) -> some View {
        Button(scopeLabel) {
            Task {
                await applyClaimBulkAction(
                    action,
                    .pageOrFolderOnly,
                    targetClaims
                )
            }
        }
        Button("Library-wide") {
            Task {
                await applyClaimBulkAction(
                    action,
                    .libraryWide,
                    targetClaims
                )
            }
        }
    }
}

struct ClaimCurationBadge: View {
    let state: Components.Schemas.ClaimCurationState

    var body: some View {
        Text(label)
            .font(.caption2)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.16), in: Capsule())
            .foregroundStyle(color)
    }

    private var label: String {
        switch state {
        case .curated:
            return "Approved"
        case .rejected:
            return "Rejected"
        case .shortlisted:
            return "Shortlisted"
        case .unreviewed:
            return "Unreviewed"
        }
    }

    private var color: Color {
        switch state {
        case .curated:
            return .green
        case .rejected:
            return .red
        case .shortlisted:
            return .orange
        case .unreviewed:
            return .gray
        }
    }
}
// swiftlint:enable file_length type_body_length
