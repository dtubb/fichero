import FicheroAPIClient
import OSLog
import SwiftUI
import UniformTypeIdentifiers

// MARK: - Document Entities Tab

// `internal` (was `private`): the tab's helpers/actions were split across
// `DocumentInspectorEntitiesTab+*.swift` extension files, which cannot see a
// file-`private` global.
let inspectorEntitiesLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "DocumentInspectorEntitiesTab"
)

struct DocumentInspectorEntitiesTab: View {
    // NOTE: The stored properties below are `internal` (not `private`). This
    // view's helpers and actions live in `DocumentInspectorEntitiesTab+*.swift`
    // extension files, and a same-type extension in a *different* file cannot
    // reference a `private` member — so every stored member touched by a moved
    // helper is `internal`.
    let document: Document
    let documentId: String
    var selectedEntityId: String?
    var onEntitySelect: ((String) -> Void)?

    /// The single endpoint accessor for this document's entities (#1885). The
    /// view no longer owns a fetched copy or calls the services directly — it
    /// observes the store and routes mutations through its named actions; the
    /// store (and, once it emits, the change-stream) republishes the list.
    @Environment(EntityStore.self) var entityStore
    @Environment(EntityService.self) var entityService
    /// Per-window entity-search bus (#3437).
    @Environment(EntitySearchState.self) var entitySearchState: EntitySearchState?
    /// Cross-view KG focus — drives "Show in Graph" (#3452).
    @Environment(KGFocusState.self) var kgFocusState
    /// Document tree — supplies a folder's children for aggregation (#3450).
    @Environment(DocumentStore.self) var documentStore
    /// Shared with the KG tab: aggregate across a folder's children when on.
    @AppStorage("inspector.scope.includeChildren") var includeChildren = false

    @State var entitySelection: Set<String> = []
    @State var isApplyingBulkAction = false
    @State var pendingMergePlan: InspectorEntityBulkSelection.MergePlan?
    @State var pendingReclassifyPlan: PendingEntityReclassifyPlan?
    @State var pendingDeleteConfirmation: PendingEntityDeleteConfirmation?
    @State var actionMessage: String?
    /// Presents the user-driven reconciliation scope picker + merge (#3318).
    @State var showReconcile = false
    @State var dropTargetEntityId: String?
    /// In-place rename state — the id of the entity whose name is being
    /// edited inline, plus the draft text. (#1865)
    @State var renamingEntityId: String?
    @State var renameDraft = ""
    @FocusState var renameFieldFocused: Bool
    @AppStorage("inspector.entities.hiddenKinds") var hiddenKindsCSV: String = ""

    // ponytail: recompute inputs — scopedEntities, hiddenKindsCSV
    @State var grouped: [(EntityKind, [Components.Schemas.KnowledgeEntity])] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Top of the tab is just content — the count, filter, refresh, and
            // selection actions all live in the bottom mini-toolbar (#3461).
            if let actionMessage {
                Text(actionMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal)
            }

            if isScopedLoading {
                ProgressView()
                    .padding(.vertical, 8)
                    .padding(.horizontal)
            } else if let loadError = scopedLoadError {
                Label(loadError, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.orange)
                    .padding(.horizontal)
            } else if scopedEntities.isEmpty {
                Text("No entities for this document yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal)
            } else if grouped.isEmpty {
                emptyVisibleGroupsState
            } else {
                VStack(spacing: 0) {
                    InspectorListDetailSplit {
                        List(selection: $entitySelection) {
                            ForEach(grouped, id: \.0) { kind, items in
                                entityKindSection(kind: kind, entities: items)
                            }
                        }
                        .listStyle(.inset)
                    } detail: {
                        entityDetailPane
                    }
                    Divider()
                    entitiesMiniToolbar
                        .padding(.horizontal, 8)
                        .padding(.vertical, 6)
                }
            }
        }
        .padding(.top)
        // The store owns fetching; the view just scopes it to this document
        // (or the folder's aggregated children when the scope toggle is on).
        .task(id: "\(documentId)-\(includeChildren)") { await loadScopedEntities() }
        .sheet(isPresented: $showReconcile) {
            EntityReconciliationSheet(documentId: documentId)
        }
        .onAppear { recomputeGrouped() }
        .onChange(of: scopedEntities) { _, _ in
            recomputeGrouped()
            syncSelectionToLoadedEntities()
        }
        .onChange(of: entitySelection) { _, _ in
            routeSelectionToInspector()
        }
        .onChange(of: selectedEntityId, initial: true) { _, _ in
            syncSelectionToFocusedEntity()
        }
        .onChange(of: hiddenKindsCSV) { _, _ in recomputeGrouped() }
        .alert(
            pendingMergePlan.map {
                "Merge \($0.entityCount) entities into \"\($0.survivorName)\"?"
            } ?? "Merge entities?",
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
            Text("This keeps \(plan.survivorName) as the canonical entity and folds the others into it.")
        }
        .alert(
            pendingReclassifyPlan?.title ?? "Change entity type?",
            isPresented: Binding(
                get: { pendingReclassifyPlan != nil },
                set: { if !$0 { pendingReclassifyPlan = nil } }
            ),
            presenting: pendingReclassifyPlan
        ) { plan in
            Button("Change Type") {
                Task { await applyReclassify(plan) }
            }
            Button("Cancel", role: .cancel) {
                pendingReclassifyPlan = nil
            }
        } message: { plan in
            Text(plan.message)
        }
        .alert(
            pendingDeleteConfirmation?.title ?? "Delete entity?",
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
    }
}
