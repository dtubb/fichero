import FicheroAPIClient
import SwiftUI

// MARK: - EntityKindRow

/// One row inside an EntityKindBlock. The **name** is tappable —
/// clicking fires a scoped entity search (e.g. `person:"…"`) via the
/// typed `EntitySearchState` request, same path Keyword
/// lozenges use. Aliases / page reference / context render as plain
/// selectable text below for ⌘C. (#882)
///
/// The row's rendering (`claimBlock` + formatting helpers) lives in
/// `EntityKindRow+ClaimBlock.swift`; focus + bulk-action handlers live in
/// `EntityKindRow+Actions.swift`. Members those extensions touch are
/// `internal` (not `private`) so the cross-file extensions can reach them.
struct EntityKindRow: View {
    /// Per-window entity-search bus (#3437); optional → safe no-op if a host
    /// hasn't injected it.
    @Environment(EntitySearchState.self) var entitySearchState: EntitySearchState?
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

    @Environment(ClaimFocusState.self) var claimFocusState
    @Environment(KGFocusState.self) var kgFocusState
    /// Crop fetch seam for the source-provenance quick-look (#3449). Optional so
    /// the popover is a safe no-op if a host hasn't injected the store — the
    /// crop just resolves to "No source region" instead of crashing.
    @Environment(AnnotationStore.self) var annotationStore: AnnotationStore?
    @AppStorage("editor.fontSize") var defaultFontSize: Double = 13
    // Configurable row metadata (#3466), Xcode-console-style — the mini-toolbar's
    // "Row Detail" menu flips these, persisted so the choice sticks across docs.
    @AppStorage("inspector.kg.row.showConfidence") var showConfidence = true
    @AppStorage("inspector.kg.row.showPageRef") var showPageRef = true
    @AppStorage("inspector.kg.row.showContext") var showContext = true
    @AppStorage("inspector.kg.row.showExcerpt") var showExcerpt = true
    /// The claim currently expanded into the inline S/V/O editor (#3463).
    @State var inlineEditingClaimId: String?
    /// Presents the source-provenance quick-look popover for the primary claim.
    @State var isSourcePreviewPresented = false

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

        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
    }
}
