#if canImport(AppKit)
import AppKit
#endif
import FicheroAPIClient
import OSLog
import SwiftUI
import UniformTypeIdentifiers

// MARK: - Entities Tab Support Types

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
        // The sidebar pipeline's named envelope, `entity:`-prefixed (Daniel
        // 2026-08-12: drag entities onto a library workspace). Riding the
        // EXISTING `ficheroDragItem` flavor — declared in Info.plist, read by
        // `readSidebarDropPayload`, degraded-envelope recovery included —
        // instead of a new UTType; the classifier tells the shapes apart by
        // prefix, exactly as it does `doc:` vs LibraryItemDrag JSON.
        DataRepresentation(exportedContentType: .ficheroDragItem) { item in
            Data("entity:\(item.id)".utf8)
        }
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

    /// Delegates to `SelectionGrammar` (#4377) — the inspector's list obeys the
    /// same Mac grammar as the library's, because there is now only one
    /// implementation of it to obey. This entry point stays because the
    /// inspector speaks its own `InspectorEntitySelectionModifiers` (built from
    /// a platform event) and has no use for the grammar's cursor.
    static func reduceTap(
        tappedId: String,
        orderedIds: [String],
        selection: Set<String>,
        anchor: String?,
        modifiers: InspectorEntitySelectionModifiers
    ) -> ReductionResult {
        var grammarModifiers: SelectionGrammar.Modifiers = []
        if modifiers.contains(.shift) { grammarModifiers.insert(.shift) }
        if modifiers.contains(.command) { grammarModifiers.insert(.command) }
        let result = SelectionGrammar.click(
            id: tappedId,
            in: orderedIds,
            selection: selection,
            anchor: anchor,
            modifiers: grammarModifiers
        )
        return ReductionResult(selection: result.selection, anchor: result.anchor)
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
