import FicheroAPIClient
import OSLog
import SwiftUI

// Promoted from `private` → internal so the `+Actions` extension file can log.
let inspectorClaimsLogger = Logger(
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
//
// The struct is split across sibling files to stay within SwiftLint's
// type/file-length budgets (see `KnowledgeGraphInspectorSection+*.swift`):
//   +Grouping        — the grouping/digest pipeline and its nested value types
//   +Views           — content region, claim list, quick-look, digest view
//   +Toolbar         — the pinned bottom mini-toolbar, filter, and menus
//   +Actions         — load / bulk-action / merge / delete / prune handlers
//   +SupportingTypes — standalone scope/confirmation/selection value types
// Members referenced from those files were promoted `private` → internal.
struct KnowledgeGraphInspectorSection: View {
    let documentId: String
    let documentScope: InspectorClaimDocumentScope
    let entityService: EntityService
    let artifactService: ArtifactService
    let kgCurationService: KGCurationService
    /// Called when the user clicks the source-page arrow on an entity row.
    /// Receives the source page document id; ContentView decides how to
    /// navigate (typically: select the parent file in the grid). Optional
    /// so previews and standalone uses still compile. (#833)
    var onNavigateToSource: ((String) -> Void)?
    /// Called when the user clicks on a claim to select it for highlighting
    var onClaimSelect: ((String, String?, String?, String?, Int?, Int?) -> Void)?

    // Promoted `private` → internal: focusClaim lives in +Actions.
    @Environment(KGFocusState.self) var kgFocusState
    // Internal, not `private`: read from +Actions.swift now that claim writes
    // route through the store (#1848). Same reason as spaceQuickLookPopover
    // below — this type spans four files, so `private` on any shared member is
    // a compile error waiting for the next extension that needs it.
    /// Observable claim store (#1862) — its `changeToken` bumps on every
    /// `claim.*` change event from the per-library change-stream, driving this
    /// section's resync. Replaces the retired `.ficheroClaim*` NotificationCenter
    /// bus; the inspector still owns its grouped KG read (iterate, never replace).
    @Environment(ClaimStore.self) var claimStore
    // Promoted `private` → internal: spaceQuickLookPopover lives in +Views.
    /// Crop fetch seam for the Space-key source quick-look (#3449/#3425). Optional
    /// so the preview is a safe no-op if a host hasn't injected the store.
    @Environment(AnnotationStore.self) var annotationStore: AnnotationStore?
    // The @State below are promoted `private` → internal: read/written from the
    // +Views / +Toolbar / +Actions extension files.
    @State private var loadState = KnowledgeGraphInspectorLoadState()
    @State var claimSelection: Set<String> = []
    @State var claimSelectionAnchor: String?
    /// The claim whose source is shown in the Space-key quick-look popover.
    @State var spaceQuickLookClaimId: String?
    @State var isApplyingBulkAction = false
    @State var isPruningTrivialClaims = false
    @State var pendingMergePlan: InspectorClaimBulkSelection.MergePlan?
    @State var pendingDeleteConfirmation: PendingClaimDeleteConfirmation?
    @State var claimActionMessage: String?
    @State var pendingPruneConfirmation: PendingPruneConfirmation?
    // Promoted `private` → internal (accessors read/written from +Actions,
    // +Views, +Grouping). `loadState` itself stays private to this file.
    var claims: [Components.Schemas.KnowledgeClaim] {
        get { loadState.claims }
        nonmutating set { loadState.claims = newValue }
    }
    var canonicalGroups: [Components.Schemas.KGEntityGroup] {
        get { loadState.canonicalGroups }
        nonmutating set { loadState.canonicalGroups = newValue }
    }
    var isLoading: Bool {
        get { loadState.isLoading }
        nonmutating set { loadState.isLoading = newValue }
    }
    var loadError: String? {
        get { loadState.loadError }
        nonmutating set { loadState.loadError = newValue }
    }
    // Promoted `private` → internal: setHidden (+Grouping) / kgFilterMenu (+Toolbar).
    /// Comma-joined raw values of EntityKinds the user has hidden from the
    /// KG list. Persisted across launches so the filter survives restarts.
    /// Default: all kinds visible.
    @AppStorage("inspector.kg.hiddenKinds") var hiddenKindsCSV: String = ""

    // Promoted `private` → internal: kgContent (+Views) / kgMiniToolbar (+Toolbar).
    /// Text = dense semicolon prose per entity; List = grouped disclosure rows.
    @AppStorage("inspector.kg.displayMode") var displayMode: KGDisplayMode = .text
    // Promoted `private` → internal: kgFilterMenu (+Toolbar) / loadStatements (+Actions).
    /// Default to the item's OWN records — a folder/PDF shows what belongs to
    /// IT, not its children's mixed in (#2697). Children are opt-in via the
    /// "Include children" scope toggle and badged ("Includes children") when on.
    @AppStorage("inspector.scope.includeChildren") var includeChildren: Bool = false
    @AppStorage("editor.fontSize") private var defaultFontSize: Double = 13
    // Configurable per-row metadata (#3466). Shared keys with EntityKindRow so the
    // "Row Detail" menu below toggles exactly what each row renders.
    // Promoted `private` → internal: rowDetailMenu lives in +Toolbar.
    @AppStorage("inspector.kg.row.showConfidence") var rowShowConfidence = true
    @AppStorage("inspector.kg.row.showPageRef") var rowShowPageRef = true
    @AppStorage("inspector.kg.row.showContext") var rowShowContext = true
    @AppStorage("inspector.kg.row.showExcerpt") var rowShowExcerpt = true

    // Promoted `private` → internal: textDigestView lives in +Views.
    var bodyTextFont: Font {
        .system(size: CGFloat(defaultFontSize))
    }

    // Promoted `private` → internal: textDigestView lives in +Views.
    var typeLabelFont: Font {
        .system(size: CGFloat(max(defaultFontSize - 2, 9)), weight: .semibold)
    }

    // Promoted `private` → internal: setHidden/groupedSections (+Grouping),
    // kgFilterMenu (+Toolbar).
    var hiddenKinds: Set<EntityKind> {
        Set(
            hiddenKindsCSV
                .split(separator: ",")
                .compactMap { EntityKind(rawValue: String($0)) }
        )
    }

    // Promoted `private` → internal: kgClaimRow (+Views), scope buttons (+Toolbar).
    var documentScopeLabel: String {
        documentScope.label
    }

    // Promoted `private` → internal: the toolbar menus in +Toolbar read this.
    var isMutatingClaims: Bool {
        isApplyingBulkAction || isPruningTrivialClaims
    }

    // Cached derivations of the grouping pipeline. Recomputed once per data change
    // (`recomputeGrouped`) instead of on every render/selection click — the #2307
    // anti-pattern this file still had (#3863). Mirrors the sibling EntitiesTab fix.
    // Inputs: claims, canonicalGroups, hiddenKindsCSV.
    // Promoted `private` → internal: read/written from +Grouping / +Views /
    // +Toolbar / +Actions.
    @State var claimsById: [String: Components.Schemas.KnowledgeClaim] = [:]
    @State var grouped: [(EntityKind, [GroupedItem])] = []
    @State var orderedClaimIds: [String] = []
    @State var textDigest: [(EntityKind, [TextDigestEntry])] = []

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
        // Regroup ONCE per data change, not per render (#3863). loadStatements sets
        // claims + canonicalGroups (fed by .task + changeToken above); the filter is
        // a client-side toggle. Reading @State grouped/orderedClaimIds/textDigest in
        // the body then costs nothing.
        .onAppear { recomputeGrouped() }
        .onChange(of: canonicalGroups) { recomputeGrouped() }
        .onChange(of: claims) { recomputeGrouped() }
        .onChange(of: hiddenKindsCSV) { recomputeGrouped() }
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
}
