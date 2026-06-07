// swiftlint:disable file_length
import AppKit
import FicheroAPIClient
import OSLog
import SwiftUI

// MARK: - Document Entities Tab

private let inspectorEntitiesLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "DocumentInspectorEntitiesTab"
)

// swiftlint:disable type_body_length
struct DocumentInspectorEntitiesTab: View {
    let document: Document
    let documentId: String
    let entityService: EntityServiceGenerated
    let kgCurationService: KGCurationServiceGenerated
    var onEntitySelect: ((String) -> Void)?

    @State private var entities: [Components.Schemas.KnowledgeEntity] = []
    @State private var entitySelection: Set<String> = []
    @State private var selectionAnchor: String?
    @State private var isLoading = false
    @State private var isApplyingBulkAction = false
    @State private var loadError: String?
    @State private var actionMessage: String?
    @AppStorage("inspector.entities.hiddenKinds") private var hiddenKindsCSV: String = ""

    private var hiddenKinds: Set<EntityKind> {
        Set(
            hiddenKindsCSV
                .split(separator: ",")
                .compactMap { EntityKind(rawValue: String($0)) }
        )
    }

    private var grouped: [(EntityKind, [Components.Schemas.KnowledgeEntity])] {
        let grouped = Dictionary(grouping: entities) { entity in
            EntityKind(apiType: entity.entityType) ?? .other
        }
        return EntityKind.displayOrder.compactMap { kind in
            guard !hiddenKinds.contains(kind), let items = grouped[kind], !items.isEmpty else {
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

    private var bulkActionScopeLabel: String {
        document.docType == .page ? "This page only" : "This folder only"
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                header
                if entitySelection.count > 1 {
                    bulkActionBar
                }
                if let actionMessage {
                    Text(actionMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if isLoading {
                    ProgressView().padding(.vertical, 8)
                } else if let loadError {
                    Label(loadError, systemImage: "exclamationmark.triangle")
                        .font(.caption)
                        .foregroundStyle(.orange)
                } else if entities.isEmpty {
                    Text("No entities for this document yet.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else if grouped.isEmpty {
                    emptyVisibleGroupsState
                } else {
                    ForEach(grouped, id: \.0) { kind, items in
                        entityKindSection(kind: kind, entities: items)
                    }
                }
            }
            .padding()
        }
        .task(id: documentId) { await loadEntities() }
    }

    private var header: some View {
        HStack(spacing: 8) {
            Text("\(entities.count) entities")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            filterMenu
            Button {
                Task { await loadEntities() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.plain)
            .help("Reload entities")
        }
    }

    private var bulkActionBar: some View {
        HStack(spacing: 8) {
            Text("\(entitySelection.count) selected")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            bulkActionMenu(title: "Approve", systemImage: "checkmark.circle", action: .approve)
            bulkActionMenu(title: "Reject", systemImage: "xmark.circle", action: .reject)
            bulkActionMenu(title: "Suppress", systemImage: "eye.slash", action: .suppress)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.secondary.opacity(0.08))
        )
    }

    @ViewBuilder
    private var emptyVisibleGroupsState: some View {
        if hasActiveKindFilter {
            VStack(alignment: .leading, spacing: 6) {
                Text("Loaded \(entities.count) entities, but the current filter hides every kind.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Button("Show all kinds") {
                    hiddenKindsCSV = ""
                }
                .buttonStyle(.link)
                .font(.caption)
            }
        } else {
            VStack(alignment: .leading, spacing: 6) {
                Label(
                    "Loaded \(entities.count) entities, but none mapped into a visible section.",
                    systemImage: "exclamationmark.triangle"
                )
                .font(.caption)
                .foregroundStyle(.orange)

                entityKindSection(kind: .other, entities: entities)
            }
        }
    }

    private var filterMenu: some View {
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
        .help("Filter entity kinds")
    }

    private func entityKindSection(
        kind: EntityKind,
        entities: [Components.Schemas.KnowledgeEntity]
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("\(kind.label.uppercased()) \(entities.count)", systemImage: kind.systemImage)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)

            ForEach(entities, id: \.stableInspectorId) { entity in
                entityRow(entity, kind: kind)
            }
        }
    }

    private func entityRow(
        _ entity: Components.Schemas.KnowledgeEntity,
        kind: EntityKind
    ) -> some View {
        let stableId = entity.stableInspectorId
        let isSelected = entitySelection.contains(stableId)
        Button {
            handleEntityTap(entity, kind: kind)
        } label: {
            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(entity.canonicalName)
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundStyle(.primary)
                    if let curationState = entity.curationState, curationState != .unreviewed {
                        EntityCurationBadge(state: curationState)
                    }
                    if let count = entity.sourceDocumentIds?.count, count > 1 {
                        Text("\(count) sources")
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
            .padding(.horizontal, 6)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isSelected ? Color.accentColor.opacity(0.16) : Color.accentColor.opacity(0.06))
            )
        }
        .buttonStyle(.plain)
        .contextMenu {
            entityContextMenu(for: entity)
        }
        .help("Inspect \(entity.canonicalName)")
    }

    private func setHidden(_ kind: EntityKind, hidden: Bool) {
        var set = hiddenKinds
        if hidden { set.insert(kind) } else { set.remove(kind) }
        hiddenKindsCSV = set.map(\.rawValue).sorted().joined(separator: ",")
    }

    private func loadEntities() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }

        do {
            let loaded = try await entityService.listInspectorEntitiesForDocument(
                documentId: documentId
            )
            inspectorEntitiesLogger.debug(
                "Loaded \(loaded.count, privacy: .public) inspector entities for \(documentId, privacy: .public)"
            )
            entities = loaded
            syncSelectionToLoadedEntities()
        } catch is CancellationError {
            // Superseded by a newer document selection.
        } catch {
            inspectorEntitiesLogger.error(
                "Failed to load inspector entities for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
            loadError = "Couldn't load entities: \(error.localizedDescription)"
            entities = []
            entitySelection = []
            selectionAnchor = nil
        }
    }

    @ViewBuilder
    private func entityContextMenu(
        for entity: Components.Schemas.KnowledgeEntity
    ) -> some View {
        let targetEntities = contextMenuTargetEntities(for: entity)
        let targetCount = targetEntities.count

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

    private func handleEntityTap(
        _ entity: Components.Schemas.KnowledgeEntity,
        kind: EntityKind
    ) {
        let stableIds = orderedEntities.map(\.stableInspectorId)
        let modifiers = InspectorEntitySelectionModifiers(nsEventFlags: NSEvent.modifierFlags)
        let reduced = InspectorEntityBulkSelection.reduceTap(
            tappedId: entity.stableInspectorId,
            orderedIds: stableIds,
            selection: entitySelection,
            anchor: selectionAnchor,
            modifiers: modifiers
        )
        entitySelection = reduced.selection
        selectionAnchor = reduced.anchor

        guard modifiers.isEmpty else { return }
        if let id = entity.id {
            onEntitySelect?(id)
        } else {
            postSearch(for: entity, kind: kind)
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

    private func syncSelectionToLoadedEntities() {
        let validIds = Set(orderedEntities.map(\.stableInspectorId))
        entitySelection = entitySelection.intersection(validIds)
        if let selectionAnchor, !validIds.contains(selectionAnchor) {
            self.selectionAnchor = nil
        }
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
            if !entityIds.isEmpty {
                _ = try await kgCurationService.batchSetEntityCurationState(
                    entityIds: entityIds,
                    curationState: action.curationState
                )
                applyLocalStateUpdate(entityIds: Set(entityIds), state: action.curationState)
            }

            if action == .suppress, scope == .libraryWide {
                if !suppressRules.isEmpty {
                    _ = try await kgCurationService.batchCreateEntityRules(suppressRules)
                }
            }

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

    private func applyLocalStateUpdate(
        entityIds: Set<String>,
        state: Components.Schemas.EntityCurationState
    ) {
        entities = entities.map { entity in
            guard let id = entity.id, entityIds.contains(id) else { return entity }
            var updated = entity
            updated.curationState = state
            return updated
        }
    }

    private func postSearch(
        for entity: Components.Schemas.KnowledgeEntity,
        kind: EntityKind
    ) {
        NotificationCenter.default.post(
            name: .ficheroEntitySearchRequested,
            object: nil,
            userInfo: [
                "name": entity.canonicalName,
                "entityType": kind.searchScope
            ]
        )
    }
}
// swiftlint:enable type_body_length

extension Components.Schemas.KnowledgeEntity {
    var stableInspectorId: String {
        id ?? "\(entityType?.rawValue ?? "other"):\(canonicalName)"
    }
}

struct InspectorEntityBulkSelection {
    struct ReductionResult {
        let selection: Set<String>
        let anchor: String?
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
                matchEntityType: entity.entityType,
                targetCanonicalName: nil,
                targetEntityType: nil,
                reason: "Bulk suppress from inspector",
                createdBy: "human"
            )
        }
    }
}

struct InspectorEntitySelectionModifiers: OptionSet {
    let rawValue: Int

    static let shift = Self(rawValue: 1 << 0)
    static let command = Self(rawValue: 1 << 1)

    init(rawValue: Int) {
        self.rawValue = rawValue
    }

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
