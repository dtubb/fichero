// swiftlint:disable file_length
#if canImport(AppKit)
import AppKit
#endif
import FicheroAPIClient
import OSLog
import SwiftUI
import UniformTypeIdentifiers

// MARK: - Document Entities Tab

private let inspectorEntitiesLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "DocumentInspectorEntitiesTab"
)

// swiftlint:disable type_body_length
struct DocumentInspectorEntitiesTab: View {
    let document: Document
    let documentId: String
    var selectedEntityId: String?
    var onEntitySelect: ((String) -> Void)?

    /// The single endpoint accessor for this document's entities (#1885). The
    /// view no longer owns a fetched copy or calls the services directly — it
    /// observes the store and routes mutations through its named actions; the
    /// store (and, once it emits, the change-stream) republishes the list.
    @Environment(EntityStore.self) private var entityStore
    @Environment(EntityServiceGenerated.self) private var entityService
    /// Per-window entity-search bus (#3437).
    @Environment(EntitySearchState.self) private var entitySearchState: EntitySearchState?
    /// Cross-view KG focus — drives "Show in Graph" (#3452).
    @Environment(KGFocusState.self) private var kgFocusState
    /// Document tree — supplies a folder's children for aggregation (#3450).
    @Environment(DocumentStore.self) private var documentStore
    /// Shared with the KG tab: aggregate across a folder's children when on.
    @AppStorage("inspector.scope.includeChildren") private var includeChildren = false

    @State private var entitySelection: Set<String> = []
    @State private var isApplyingBulkAction = false
    @State private var pendingMergePlan: InspectorEntityBulkSelection.MergePlan?
    @State private var pendingReclassifyPlan: PendingEntityReclassifyPlan?
    @State private var pendingDeleteConfirmation: PendingEntityDeleteConfirmation?
    @State private var actionMessage: String?
    /// Presents the user-driven reconciliation scope picker + merge (#3318).
    @State private var showReconcile = false
    @State private var dropTargetEntityId: String?
    /// In-place rename state — the id of the entity whose name is being
    /// edited inline, plus the draft text. (#1865)
    @State private var renamingEntityId: String?
    @State private var renameDraft = ""
    @FocusState private var renameFieldFocused: Bool
    @AppStorage("inspector.entities.hiddenKinds") private var hiddenKindsCSV: String = ""

    private var hiddenKinds: Set<EntityKind> {
        Set(
            hiddenKindsCSV
                .split(separator: ",")
                .compactMap { EntityKind(rawValue: String($0)) }
        )
    }

    // ponytail: recompute inputs — scopedEntities, hiddenKindsCSV
    @State private var grouped: [(EntityKind, [Components.Schemas.KnowledgeEntity])] = []

    private func recomputeGrouped() {
        let dict = Dictionary(grouping: scopedEntities) { entity in
            EntityKind(apiType: entity.entityType) ?? .other
        }
        let hidden = hiddenKinds
        grouped = EntityKind.displayOrder.compactMap { kind in
            guard !hidden.contains(kind), let items = dict[kind], !items.isEmpty else {
                return nil
            }
            return (kind, items.sorted { lhs, rhs in
                lhs.canonicalName.localizedCaseInsensitiveCompare(rhs.canonicalName) == .orderedAscending
            })
        }
    }

    private var hasActiveKindFilter: Bool {
        !hiddenKinds.isEmpty
    }

    private var orderedEntities: [Components.Schemas.KnowledgeEntity] {
        grouped.flatMap(\.1)
    }

    private var selectedEntities: [Components.Schemas.KnowledgeEntity] {
        orderedEntities.filter { entitySelection.contains($0.stableInspectorId) }
    }

    private var selectedEntity: Components.Schemas.KnowledgeEntity? {
        guard entitySelection.count == 1 else { return nil }
        return selectedEntities.first
    }

    private var scopedEntities: [Components.Schemas.KnowledgeEntity] {
        entityStore.entities(forDocument: documentId)
    }

    private var isFolder: Bool { document.docType == .folder }

    /// Aggregate across children when a folder is inspected and the scope toggle
    /// is on (#3450); otherwise the entities are just this document's.
    private var aggregatingChildren: Bool { isFolder && includeChildren }

    /// Load entities for the current scope: a folder's aggregated children, or a
    /// single document. Published under `documentId`, so `scopedEntities` reads
    /// the right set either way.
    private func loadScopedEntities(force: Bool = false) async {
        if aggregatingChildren {
            let childIds = await documentStore.children(of: documentId).map(\.id)
            await entityStore.loadAggregatedEntities(
                forFolder: documentId,
                childDocumentIds: childIds,
                force: force
            )
        } else {
            await entityStore.loadEntities(forDocument: documentId, force: force)
        }
    }

    private var scopedLoadError: String? {
        entityStore.loadError(forDocument: documentId)
    }

    private var isScopedLoading: Bool {
        entityStore.isLoading(forDocument: documentId)
    }

    private var bulkActionScopeLabel: String {
        document.docType == .page ? "This page only" : "This folder only"
    }

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

    private var entitiesMiniToolbar: some View {
        InspectorBottomMiniToolbar(statusText: entitiesToolbarStatusText) {
            filterMenu

            Button {
                Task { await loadScopedEntities(force: true) }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.plain)
            .help("Reload entities")
            .accessibilityLabel("Reload entities")

            Button {
                showReconcile = true
            } label: {
                Image(systemName: "arrow.triangle.merge")
            }
            .buttonStyle(.plain)
            .help("Reconcile duplicate entities — choose a scope (folder or library)")
            .accessibilityLabel("Reconcile entities")

            if entitySelection.count > 1 {
                bulkActionMenu(title: "Approve", systemImage: "checkmark.circle", action: .approve)
                bulkActionMenu(title: "Reject", systemImage: "xmark.circle", action: .reject)
                bulkActionMenu(title: "Suppress", systemImage: "eye.slash", action: .suppress)
                mergeActionMenu(targetEntities: selectedEntities, menuTitle: "Merge")
                deleteActionButton(targetEntities: selectedEntities)
            }
        }
    }

    private var entitiesToolbarStatusText: String {
        if let selectedEntity {
            return selectedEntity.canonicalName
        }
        return "\(scopedEntities.count) entities"
    }

    @ViewBuilder
    private var entityDetailPane: some View {
        if let entity = selectedEntity {
            EntityDigestContent(entity: entity, entityService: entityService)
                .frame(minHeight: 180, maxHeight: .infinity)
        } else if entitySelection.count > 1 {
            ContentUnavailableView(
                "Multiple Entities Selected",
                systemImage: "person.2",
                description: Text("Select a single entity to inspect it below.")
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ContentUnavailableView(
                "No Entity Selected",
                systemImage: "person.crop.circle",
                description: Text("Select an entity above to inspect it below.")
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    @ViewBuilder
    private var emptyVisibleGroupsState: some View {
        if hasActiveKindFilter {
            VStack(alignment: .leading, spacing: 6) {
                Text("Loaded \(scopedEntities.count) entities, but the current filter hides every kind.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Button("Show all kinds") {
                    hiddenKindsCSV = ""
                }
                #if os(macOS)
                .buttonStyle(.link)
                #endif
                .font(.caption)
            }
        } else {
            VStack(alignment: .leading, spacing: 6) {
                Label(
                    "Loaded \(scopedEntities.count) entities, but none mapped into a visible section.",
                    systemImage: "exclamationmark.triangle"
                )
                .font(.caption)
                .foregroundStyle(.orange)
                .padding(.horizontal)

                List(selection: $entitySelection) {
                    entityKindSection(kind: .other, entities: scopedEntities)
                }
                .listStyle(.inset)
                .frame(maxHeight: .infinity)
            }
        }
    }

    private var filterMenu: some View {
        Menu {
            // Folder aggregation scope (#3450) — only meaningful for a folder.
            if isFolder {
                Section("Scope") {
                    Button {
                        includeChildren = false
                    } label: {
                        HStack {
                            Text("This folder only")
                            Spacer(minLength: 0)
                            if !includeChildren { Image(systemName: "checkmark") }
                        }
                    }
                    Button {
                        includeChildren = true
                    } label: {
                        HStack {
                            Text("Include children")
                            Spacer(minLength: 0)
                            if includeChildren { Image(systemName: "checkmark") }
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
        .help("Filter entity kinds")
        .accessibilityLabel("Filter entity kinds")
    }

    private func entityKindSection(
        kind: EntityKind,
        entities: [Components.Schemas.KnowledgeEntity]
    ) -> some View {
        Section {
            ForEach(entities, id: \.stableInspectorId) { entity in
                entityRow(entity)
            }
        } header: {
            Label("\(kind.label.uppercased()) \(entities.count)", systemImage: kind.systemImage)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
        }
    }

    private func entityRow(
        _ entity: Components.Schemas.KnowledgeEntity
    ) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                entityNameView(for: entity)
                if let curationState = entity.curationState, curationState != .unreviewed {
                    EntityCurationBadge(state: curationState)
                }
                if let count = entity.sourceDocumentIds?.count, count > 1 {
                    Text("Includes children")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
            }
            if let aliases = entity.aliases, !aliases.isEmpty {
                Text(aliases.prefix(3).joined(separator: ", "))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            if let description = entity.description, !description.isEmpty {
                Text(description)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 4)
        .background(dropTargetHighlight(for: entity))
        .inspectorListRowTarget()
        .tag(entity.stableInspectorId)
        .draggable(InspectorEntityDragID(id: entity.stableInspectorId, text: entity.canonicalName))
        .dropDestination(
            for: InspectorEntityDragID.self,
            action: { payloads, _ in
                handleEntityDrop(payloads: payloads, onto: entity)
            },
            isTargeted: dropTargetHandler(for: entity)
        )
        .simultaneousGesture(
            TapGesture(count: 2).onEnded { openEntity(entity) }
        )
        .contextMenu { entityContextMenu(for: entity) }
        .help("Inspect \(entity.canonicalName)")
    }

    /// Canonical name — double-click the name (or use the Rename context
    /// action) to swap in an inline TextField. Enter commits, Esc cancels.
    /// `highPriorityGesture` so the name's double-click beats the row's
    /// double-click-to-open. (#1865)
    @ViewBuilder
    private func entityNameView(
        for entity: Components.Schemas.KnowledgeEntity
    ) -> some View {
        if renamingEntityId == entity.stableInspectorId {
            TextField("Name", text: $renameDraft)
                .textFieldStyle(.plain)
                .font(.caption.weight(.semibold))
                .focused($renameFieldFocused)
                .onSubmit { commitRename(for: entity) }
                #if os(macOS)
                .onExitCommand { cancelRename() }
                #endif
                .onAppear { renameFieldFocused = true }
        } else {
            // Plain, readable name — no link styling. The accent-underlined
            // button was unreadable when the row highlight inverted, and its
            // single-click search intercepted the row's hit target so only a
            // narrow strip selected. The name is now plain text: the whole row
            // selects (List + tag), double-click renames, and "Find in Library"
            // moved to the context menu.
            Text(entity.canonicalName)
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundStyle(.primary)
                .help("Double-click to rename \"\(entity.canonicalName)\"")
                .simultaneousGesture(
                    TapGesture(count: 2).onEnded { beginRename(entity) }
                )
        }
    }

    private func beginRename(_ entity: Components.Schemas.KnowledgeEntity) {
        guard entity.id != nil else { return }
        renameDraft = entity.canonicalName
        renamingEntityId = entity.stableInspectorId
    }

    private func cancelRename() {
        renamingEntityId = nil
        renameFieldFocused = false
    }

    /// Commit the inline rename through the entity store; the store PATCHes and
    /// republishes the list. The backend emits `entity.updated`, so the
    /// change-stream fans the refresh to other surfaces (EntityDetailView header)
    /// — the `.ficheroEntityUpdated` NotificationCenter nudge is now retired (#1862/#1865).
    private func commitRename(for entity: Components.Schemas.KnowledgeEntity) {
        let trimmed = renameDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        renamingEntityId = nil
        renameFieldFocused = false
        guard let entityId = entity.id,
              !trimmed.isEmpty,
              trimmed != entity.canonicalName else { return }

        Task {
            do {
                try await entityStore.rename(entityId: entityId, to: trimmed)
            } catch {
                inspectorEntitiesLogger.error(
                    "Entity rename failed for \(entityId, privacy: .public): \(error.localizedDescription, privacy: .public)"
                )
                actionMessage = "Couldn't rename entity: \(error.localizedDescription)"
            }
        }
    }

    private func setHidden(_ kind: EntityKind, hidden: Bool) {
        var set = hiddenKinds
        if hidden { set.insert(kind) } else { set.remove(kind) }
        hiddenKindsCSV = set.map(\.rawValue).sorted().joined(separator: ",")
    }

    @ViewBuilder
    private func entityContextMenu(
        for entity: Components.Schemas.KnowledgeEntity
    ) -> some View {
        let targetEntities = contextMenuTargetEntities(for: entity)
        let targetCount = targetEntities.count

        Button("Rename") { beginRename(entity) }
            .disabled(entity.id == nil)
        Button("Find in Library") {
            postSearch(for: entity, kind: EntityKind(apiType: entity.entityType) ?? .other)
        }
        // Row text can't use .textSelection (it fights row selection), so Copy
        // is the always-available copy-paste path for a selectable row (#3461).
        Button("Copy Name") {
            #if canImport(AppKit)
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(entity.canonicalName, forType: .string)
            #endif
        }
        if let entityId = entity.id {
            Button("Show in Graph") {
                kgFocusState.requestGraphReveal(entityId: entityId)
            }
        }
        Divider()

        Menu("Approve") {
            bulkScopeButtons(
                action: .approve,
                targetEntities: targetEntities
            )
        }
        .disabled(isApplyingBulkAction || targetCount == 0)

        Menu("Reject") {
            bulkScopeButtons(
                action: .reject,
                targetEntities: targetEntities
            )
        }
        .disabled(isApplyingBulkAction || targetCount == 0)

        Menu("Suppress") {
            bulkScopeButtons(
                action: .suppress,
                targetEntities: targetEntities
            )
        }
        .disabled(isApplyingBulkAction || targetCount == 0)

        mergeActionMenu(targetEntities: targetEntities, menuTitle: "Merge")
        deleteContextMenuButton(targetEntities: targetEntities)
    }

    @ViewBuilder
    private func bulkScopeButtons(
        action: InspectorEntityBulkAction,
        targetEntities: [Components.Schemas.KnowledgeEntity]
    ) -> some View {
        Button(bulkActionScopeLabel) {
            Task {
                await applyBulkAction(
                    action,
                    scope: .pageOrFolderOnly,
                    targetEntities: targetEntities
                )
            }
        }
        Button("Library-wide") {
            Task {
                await applyBulkAction(
                    action,
                    scope: .libraryWide,
                    targetEntities: targetEntities
                )
            }
        }
    }

    private func bulkActionMenu(
        title: String,
        systemImage: String,
        action: InspectorEntityBulkAction
    ) -> some View {
        Menu {
            bulkScopeButtons(action: action, targetEntities: selectedEntities)
        } label: {
            Label(title, systemImage: systemImage)
        }
        .menuStyle(.borderlessButton)
        .disabled(isApplyingBulkAction || selectedEntities.isEmpty)
    }

    private func mergeActionMenu(
        targetEntities: [Components.Schemas.KnowledgeEntity],
        menuTitle: String
    ) -> some View {
        // One destination choice per candidate so the user picks which entity
        // the others fold INTO (#2499). The heuristic survivor is marked
        // Recommended; picking any sets the confirmation plan.
        let recommendedId = InspectorEntityBulkSelection.mergeSurvivor(in: targetEntities)?.id
        let canMerge = InspectorEntityBulkSelection.mergePlan(for: targetEntities) != nil
        return Menu {
            if canMerge {
                ForEach(targetEntities, id: \.stableInspectorId) { entity in
                    if let id = entity.id,
                       let plan = InspectorEntityBulkSelection.mergePlan(
                            for: targetEntities, survivorId: id) {
                        Button(mergeDestinationLabel(
                            name: entity.canonicalName,
                            isRecommended: id == recommendedId
                        )) {
                            pendingMergePlan = plan
                        }
                    }
                }
            } else {
                Button("Requires 2+ same-kind saved entities") {}
                    .disabled(true)
            }
        } label: {
            Label(menuTitle, systemImage: "arrow.triangle.merge")
        }
        .menuStyle(.borderlessButton)
        .disabled(isApplyingBulkAction || !canMerge)
    }

    /// Menu-button title for a merge destination (#2499). Marks the heuristic
    /// survivor as "(Recommended)" so the sensible default is one click away.
    private func mergeDestinationLabel(name: String, isRecommended: Bool) -> String {
        isRecommended ? "Into \"\(name)\" (Recommended)" : "Into \"\(name)\""
    }

    private func deleteActionButton(
        targetEntities: [Components.Schemas.KnowledgeEntity]
    ) -> some View {
        Button(role: .destructive) {
            requestDeleteAction(for: targetEntities)
        } label: {
            Label("Delete", systemImage: "trash")
        }
        .buttonStyle(.borderless)
        .disabled(isApplyingBulkAction || targetEntities.isEmpty)
    }

    @ViewBuilder
    private func deleteContextMenuButton(
        targetEntities: [Components.Schemas.KnowledgeEntity]
    ) -> some View {
        Button("Delete…", role: .destructive) {
            requestDeleteAction(for: targetEntities)
        }
        .disabled(isApplyingBulkAction || targetEntities.isEmpty)
    }

    /// Single-click selects (native List); double-click opens the entity. (Finder-style.)
    private func openEntity(_ entity: Components.Schemas.KnowledgeEntity) {
        if let id = entity.id {
            onEntitySelect?(id)
        } else {
            postSearch(for: entity, kind: EntityKind(apiType: entity.entityType) ?? .other)
        }
    }

    private func contextMenuTargetEntities(
        for entity: Components.Schemas.KnowledgeEntity
    ) -> [Components.Schemas.KnowledgeEntity] {
        if entitySelection.contains(entity.stableInspectorId) {
            return selectedEntities
        }
        return [entity]
    }

    private func requestDeleteAction(for targetEntities: [Components.Schemas.KnowledgeEntity]) {
        pendingDeleteConfirmation = PendingEntityDeleteConfirmation(entities: targetEntities)
    }

    private func syncSelectionToLoadedEntities() {
        let validIds = Set(orderedEntities.map(\.stableInspectorId))
        entitySelection = entitySelection.intersection(validIds)
        syncSelectionToFocusedEntity()
    }

    private func syncSelectionToFocusedEntity() {
        guard let selectedEntityId,
              let entity = orderedEntities.first(where: { $0.id == selectedEntityId }) else { return }
        let stableId = entity.stableInspectorId
        guard entitySelection != [stableId] else { return }
        entitySelection = [stableId]
    }

    private func routeSelectionToInspector() {
        guard entitySelection.count == 1,
              let entity = selectedEntities.first,
              let id = entity.id else { return }
        onEntitySelect?(id)
    }

    private func dropTargetHandler(
        for entity: Components.Schemas.KnowledgeEntity
    ) -> (Bool) -> Void {
        { isTargeted in
            if isTargeted {
                dropTargetEntityId = entity.stableInspectorId
            } else if dropTargetEntityId == entity.stableInspectorId {
                dropTargetEntityId = nil
            }
        }
    }

    @ViewBuilder
    private func dropTargetHighlight(
        for entity: Components.Schemas.KnowledgeEntity
    ) -> some View {
        RoundedRectangle(cornerRadius: 8)
            .fill(
                dropTargetEntityId == entity.stableInspectorId
                    ? Color.accentColor.opacity(0.14)
                    : Color.clear
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(
                        dropTargetEntityId == entity.stableInspectorId
                            ? Color.accentColor
                            : Color.clear,
                        lineWidth: 1
                    )
            )
            .allowsHitTesting(false)
    }

    private func handleEntityDrop(
        payloads: [InspectorEntityDragID],
        onto target: Components.Schemas.KnowledgeEntity
    ) -> Bool {
        dropTargetEntityId = nil
        guard let payload = payloads.first,
              payload.id != target.stableInspectorId,
              let dragged = orderedEntities.first(where: { $0.stableInspectorId == payload.id }) else {
            return false
        }

        let draggedKind = EntityKind(apiType: dragged.entityType) ?? .other
        let targetKind = EntityKind(apiType: target.entityType) ?? .other

        if draggedKind == targetKind,
           let targetId = target.id,
           let plan = InspectorEntityBulkSelection.mergePlan(
                for: [dragged, target],
                survivorId: targetId
           ) {
            pendingMergePlan = plan
            return true
        }

        guard let draggedId = dragged.id,
              let targetType = targetKind.apiTypeId,
              draggedKind.apiTypeId != targetType else {
            return false
        }

        pendingReclassifyPlan = PendingEntityReclassifyPlan(
            entityId: draggedId,
            entityName: dragged.canonicalName,
            entityType: targetType,
            targetLabel: targetKind.label
        )
        return true
    }

    private func applyBulkAction(
        _ action: InspectorEntityBulkAction,
        scope: InspectorEntityBulkActionScope,
        targetEntities: [Components.Schemas.KnowledgeEntity]
    ) async {
        let entityIds = targetEntities.compactMap(\.id)
        let missingIdCount = targetEntities.count - entityIds.count
        guard !entityIds.isEmpty || (action == .suppress && scope == .libraryWide) else {
            actionMessage = "Selected entities are missing IDs, so \(action.verb.lowercased()) was skipped."
            return
        }

        isApplyingBulkAction = true
        actionMessage = nil
        defer { isApplyingBulkAction = false }

        do {
            let suppressRules = action == .suppress && scope == .libraryWide
                ? InspectorEntityBulkSelection.libraryWideSuppressRules(for: targetEntities)
                : []
            try await entityStore.setCuration(
                entityIds: entityIds,
                to: action.curationState,
                suppressRules: suppressRules
            )

            var message = "\(action.verb) \(entityIds.count) entit"
            message += entityIds.count == 1 ? "y" : "ies"
            if action == .suppress, scope == .libraryWide {
                message += " and wrote \(suppressRules.count) suppress rule"
                message += suppressRules.count == 1 ? "" : "s"
            }
            if missingIdCount > 0 {
                message += "; skipped \(missingIdCount) without IDs"
            }
            actionMessage = message
        } catch {
            inspectorEntitiesLogger.error(
                "Bulk entity action failed for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
            actionMessage = "Couldn't \(action.verb.lowercased()) entities: \(error.localizedDescription)"
        }
    }

    private func applyMerge(_ plan: InspectorEntityBulkSelection.MergePlan) async {
        isApplyingBulkAction = true
        actionMessage = nil
        pendingMergePlan = nil
        defer { isApplyingBulkAction = false }

        do {
            try await entityStore.merge(
                absorbedIds: plan.absorbedEntityIds,
                into: plan.survivorId
            )
            actionMessage = "Merged \(plan.entityCount) entities into \(plan.survivorName)."
            restoreSelectionAfterEntityRefresh(entityId: plan.survivorId)
        } catch {
            inspectorEntitiesLogger.error(
                "Entity merge failed for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
            actionMessage = "Couldn't merge entities: \(error.localizedDescription)"
        }
    }

    private func restoreSelectionAfterEntityRefresh(entityId: String) {
        guard let entity = orderedEntities.first(where: { $0.id == entityId }) else {
            entitySelection = []
            return
        }
        entitySelection = [entity.stableInspectorId]
        onEntitySelect?(entityId)
    }

    private func applyReclassify(_ plan: PendingEntityReclassifyPlan) async {
        isApplyingBulkAction = true
        actionMessage = nil
        pendingReclassifyPlan = nil
        defer { isApplyingBulkAction = false }

        do {
            try await entityStore.reclassify(entityId: plan.entityId, to: plan.entityType)
            actionMessage = "Changed \(plan.entityName) to \(plan.targetLabel.lowercased())."
            restoreSelectionAfterEntityRefresh(entityId: plan.entityId)
        } catch {
            inspectorEntitiesLogger.error(
                "Entity type change failed for \(plan.entityId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
            actionMessage = "Couldn't change entity type: \(error.localizedDescription)"
        }
    }

    private func applyDelete(_ pending: PendingEntityDeleteConfirmation) async {
        let entityIds = pending.entities.compactMap(\.id)
        let missingIdCount = pending.entities.count - entityIds.count
        guard !entityIds.isEmpty else {
            actionMessage = "Selected entities are missing IDs, so delete was skipped."
            pendingDeleteConfirmation = nil
            return
        }

        isApplyingBulkAction = true
        actionMessage = nil
        pendingDeleteConfirmation = nil
        defer { isApplyingBulkAction = false }

        do {
            try await entityStore.delete(entityIds: entityIds)
            entitySelection = []

            var message = "Deleted \(entityIds.count) entit"
            message += entityIds.count == 1 ? "y" : "ies"
            if missingIdCount > 0 {
                message += "; skipped \(missingIdCount) without IDs"
            }
            actionMessage = message
        } catch {
            inspectorEntitiesLogger.error(
                "Entity delete failed for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
            actionMessage = "Couldn't delete entities: \(error.localizedDescription)"
        }
    }

    private func postSearch(
        for entity: Components.Schemas.KnowledgeEntity,
        kind: EntityKind
    ) {
        entitySearchState?.request(
            name: entity.canonicalName,
            entityType: kind.searchScope
        )
    }
}
// swiftlint:enable type_body_length

extension Components.Schemas.KnowledgeEntity {
    var stableInspectorId: String {
        id ?? "\(entityType?.rawValue ?? "other"):\(canonicalName)"
    }
}

/// The drag payload for an inspector entity (#3425). Carries the stable id (for
/// in-app entity merge / reclassify drops) plus the canonical name, and defines
/// cross-target pasteboard semantics so a dragged entity behaves natively no
/// matter where it lands:
///   - a structured JSON representation that survives across the app's targets
///     and scenes (the in-app drop destinations decode this), and
///   - a plain-text representation (the entity name) so dragging an entity into
///     a text field, note, or another app pastes something meaningful.
struct InspectorEntityDragID: Codable, Transferable {
    let id: String
    var text: String = ""

    static var transferRepresentation: some TransferRepresentation {
        CodableRepresentation(contentType: .json)
        ProxyRepresentation(exporting: \.text)
    }
}

struct InspectorEntityBulkSelection {
    struct ReductionResult {
        let selection: Set<String>
        let anchor: String?
    }

    struct MergePlan: Equatable, Identifiable {
        let survivorId: String
        let absorbedEntityIds: [String]
        let survivorName: String
        let entityCount: Int

        var id: String {
            "\(survivorId):\(absorbedEntityIds.sorted().joined(separator: ","))"
        }
    }

    static func reduceTap(
        tappedId: String,
        orderedIds: [String],
        selection: Set<String>,
        anchor: String?,
        modifiers: InspectorEntitySelectionModifiers
    ) -> ReductionResult {
        if modifiers.contains(.shift),
           let anchor,
           let anchorIndex = orderedIds.firstIndex(of: anchor),
           let tappedIndex = orderedIds.firstIndex(of: tappedId) {
            let range = min(anchorIndex, tappedIndex)...max(anchorIndex, tappedIndex)
            let rangeIds = Set(orderedIds[range])
            if modifiers.contains(.command) {
                return ReductionResult(selection: selection.union(rangeIds), anchor: anchor)
            }
            return ReductionResult(selection: rangeIds, anchor: anchor)
        }

        if modifiers.contains(.command) {
            var updated = selection
            if updated.contains(tappedId) {
                updated.remove(tappedId)
            } else {
                updated.insert(tappedId)
            }
            return ReductionResult(selection: updated, anchor: tappedId)
        }

        return ReductionResult(selection: [tappedId], anchor: tappedId)
    }

    static func libraryWideSuppressRules(
        for entities: [Components.Schemas.KnowledgeEntity]
    ) -> [Components.Schemas.EntityRuleCreateRequest] {
        var seen = Set<String>()
        return entities.compactMap { entity in
            let canonicalName = entity.canonicalName.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !canonicalName.isEmpty else { return nil }
            let dedupeKey = canonicalName.lowercased()
            guard seen.insert(dedupeKey).inserted else { return nil }
            return Components.Schemas.EntityRuleCreateRequest(
                ruleType: .suppress,
                matchCanonicalName: canonicalName,
                matchEntityType: nil,
                targetCanonicalName: nil,
                targetEntityType: nil,
                reason: "Bulk suppress from inspector",
                createdBy: "human"
            )
        }
    }

    /// Merge plan using the heuristic survivor (`mergeSurvivor`) as the
    /// destination — the default/recommended choice.
    static func mergePlan(
        for entities: [Components.Schemas.KnowledgeEntity]
    ) -> MergePlan? {
        guard let survivorId = mergeSurvivor(in: entities)?.id else { return nil }
        return mergePlan(for: entities, survivorId: survivorId)
    }

    /// Merge plan with a caller-chosen survivor so the user can pick which
    /// entity is the merge DESTINATION (#2499). `survivorId` must be one of
    /// `entities`; the rest fold into it. Same validity gates as the heuristic
    /// path (2+ entities, single kind, all have IDs).
    static func mergePlan(
        for entities: [Components.Schemas.KnowledgeEntity],
        survivorId: String
    ) -> MergePlan? {
        guard entities.count > 1 else { return nil }

        let kinds = Set(entities.map { EntityKind(apiType: $0.entityType) ?? .other })
        guard kinds.count == 1,
              let survivor = entities.first(where: { $0.id == survivorId })
        else {
            return nil
        }

        let entityIds = entities.compactMap(\.id)
        guard entityIds.count == entities.count else { return nil }

        let absorbedEntityIds = entityIds.filter { $0 != survivorId }
        guard !absorbedEntityIds.isEmpty else { return nil }

        return MergePlan(
            survivorId: survivorId,
            absorbedEntityIds: absorbedEntityIds,
            survivorName: survivor.canonicalName,
            entityCount: entities.count
        )
    }

    static func mergeSurvivor(
        in entities: [Components.Schemas.KnowledgeEntity]
    ) -> Components.Schemas.KnowledgeEntity? {
        entities.sorted { lhs, rhs in
            let lhsCorroboration = lhs.corroborationCount ?? 0
            let rhsCorroboration = rhs.corroborationCount ?? 0
            if lhsCorroboration != rhsCorroboration {
                return lhsCorroboration > rhsCorroboration
            }
            if lhs.canonicalName.count != rhs.canonicalName.count {
                return lhs.canonicalName.count > rhs.canonicalName.count
            }

            let lexical = lhs.canonicalName.localizedCaseInsensitiveCompare(rhs.canonicalName)
            if lexical != .orderedSame {
                return lexical == .orderedAscending
            }
            return (lhs.id ?? "") < (rhs.id ?? "")
        }.first
    }
}

struct InspectorEntitySelectionModifiers: OptionSet {
    let rawValue: Int

    static let shift = Self(rawValue: 1 << 0)
    static let command = Self(rawValue: 1 << 1)

    init(rawValue: Int) {
        self.rawValue = rawValue
    }

    #if os(macOS)
    init(nsEventFlags: NSEvent.ModifierFlags) {
        var value: Self = []
        if nsEventFlags.contains(.shift) {
            value.insert(.shift)
        }
        if nsEventFlags.contains(.command) {
            value.insert(.command)
        }
        self = value
    }
    #else
    init(uiEventFlags: UIKeyModifierFlags) {
        var value: Self = []
        if uiEventFlags.contains(.shift) {
            value.insert(.shift)
        }
        if uiEventFlags.contains(.command) {
            value.insert(.command)
        }
        self = value
    }
    #endif
}

enum InspectorEntityBulkAction {
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

    var curationState: Components.Schemas.EntityCurationState {
        switch self {
        case .approve: return .verified
        case .reject, .suppress: return .rejected
        }
    }
}

enum InspectorEntityBulkActionScope {
    case pageOrFolderOnly
    case libraryWide
}

struct PendingEntityDeleteConfirmation: Identifiable {
    let entities: [Components.Schemas.KnowledgeEntity]

    var id: String {
        entities.map(\.stableInspectorId).sorted().joined(separator: "|")
    }

    var title: String {
        if entities.count == 1, let name = entities.first?.canonicalName {
            return "Delete \"\(name)\"?"
        }
        return "Delete \(entities.count) entities?"
    }

    var message: String {
        if entities.count == 1 {
            return "This removes the entity and any claims that reference it from the knowledge graph."
        }
        return "This removes the selected entities and any claims that reference them from the knowledge graph."
    }
}

struct PendingEntityReclassifyPlan: Identifiable {
    let entityId: String
    let entityName: String
    let entityType: String
    let targetLabel: String

    var id: String { "\(entityId):\(entityType)" }
    var title: String { "Change \"\(entityName)\" to \(targetLabel)?" }
    var message: String {
        "This changes the dragged entity's type to match the drop target."
    }
}

struct EntityCurationBadge: View {
    let state: Components.Schemas.EntityCurationState

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
        case .verified:
            return "Approved"
        case .rejected:
            return "Rejected"
        default:
            return "Unreviewed"
        }
    }

    private var color: Color {
        switch state {
        case .verified:
            return .green
        case .rejected:
            return .red
        default:
            return .gray
        }
    }
}
// swiftlint:enable file_length
