import FicheroAPIClient
import OSLog
import SwiftUI

// The content region of KnowledgeGraphInspectorSection — the text digest, the
// native claim List, the Space-key source quick-look, and the row builder.
// Split out of the core file to stay within SwiftLint's file-length budget.
extension KnowledgeGraphInspectorSection {
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
                            // Pre-rendered in recomputeGrouped (#3863).
                            Text(entry.attributed)
                                .font(bodyTextFont)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
        }
        .textSelection(.enabled)
    }

    // Promoted `private` → internal: rendered by `body` in the core file.
    /// Content region: a native List (keyboard nav + multi-select) in list
    /// mode; a ScrollView for the text digest / loading / empty states.
    @ViewBuilder
    var kgContent: some View {
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
        // Quick Look: Space on the selected claim previews its source region,
        // Xcode-console style (#3449 item 12 extension). Only fires when the
        // claim has a resolvable source anchor, else Space falls through.
        .onKeyPress(.space) {
            guard claimSelection.count == 1,
                  let id = claimSelection.first,
                  let claim = claimsById[id],
                  ClaimSummaryCard.openClaimSourceRequest(for: claim) != nil else {
                return .ignored
            }
            spaceQuickLookClaimId = id
            return .handled
        }
        .popover(isPresented: Binding(
            get: { spaceQuickLookClaimId != nil },
            set: { if !$0 { spaceQuickLookClaimId = nil } }
        )) {
            spaceQuickLookPopover
        }
    }

    /// Source quick-look popover for the Space-selected claim — reuses the same
    /// SourceProvenanceCard as the hover affordance; Reveal drives the Preview.
    @ViewBuilder
    private var spaceQuickLookPopover: some View {
        if let id = spaceQuickLookClaimId,
           let claim = claimsById[id],
           let request = ClaimSummaryCard.openClaimSourceRequest(for: claim) {
            SourceProvenanceCard(
                request: request,
                attribution: ClaimAttribution(claim: claim),
                fetch: { try await annotationStore?.cropRegion($0) ?? nil },
                onReveal: {
                    spaceQuickLookClaimId = nil
                    if let docId = claim.sourceDocumentId {
                        onNavigateToSource?(docId)
                    }
                }
            )
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
}
