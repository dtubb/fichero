import Foundation

/// Assigning a hand to the selection, the same on every surface that holds text (#5161; `source.hand.attributed`): the row
/// menu, the Reader's line menu, the Edit menu and the Inspector build their calls here, so no surface has a hand verb
/// another lacks. One segment is `hand.attribute`; several are one `hand.attribute_many` (one audit row, one ⌘Z).
enum HandAssignment {
    /// One audited action: the engine's name, the title the undo step carries, and the body.
    struct Call {
        let action: String
        let name: String
        let params: any Encodable & Sendable
    }

    static func attribute(handId: String, segmentIds: [String]) -> Call? {
        let ids = Array(NSOrderedSet(array: segmentIds)) as? [String] ?? segmentIds
        switch ids.count {
        case 0: return nil
        case 1:
            return Call(action: "hand.attribute", name: "Attribute Hand", params: HandAttributeRequest(handId: handId, segmentId: ids[0]))
        default:
            return Call(
                action: "hand.attribute_many", name: "Attribute Hand to \(ids.count) Segments",
                params: HandAttributeManyRequest(handId: handId, segmentIds: ids)
            )
        }
    }

    /// Remove Hand: every live attribution on the selection, the file's included (it is kept in the record, withdrawn).
    static func remove(selection: [String], attributions: [String: [InspectorHands.Attribution]]) -> Call? {
        let ids = Array(NSOrderedSet(array: selection.flatMap { attributions[$0] ?? [] }.map(\.id))) as? [String] ?? []
        switch ids.count {
        case 0: return nil
        case 1: return Call(action: "hand.unattribute", name: "Withdraw Attribution", params: HandUnattributeRequest(attributionId: ids[0]))
        default:
            return Call(
                action: "hand.unattribute_many", name: "Remove Hand from \(selection.count) Segments",
                params: HandUnattributeManyRequest(attributionIds: ids)
            )
        }
    }

    /// What the selection's hand is: "No hand", the hand label(s) when every segment has the same, else "Mixed".
    static func summary(
        selection: [String], attributions: [String: [InspectorHands.Attribution]], hands: [InspectorHands.ListedHand]
    ) -> String {
        guard !selection.isEmpty else { return "No hand" }
        let sets = selection.map { Set((attributions[$0] ?? []).map(\.handId)) }
        guard let first = sets.first, sets.allSatisfy({ $0 == first }) else { return "Mixed" }
        if first.isEmpty { return "No hand" }
        let labels = Dictionary(hands.map { ($0.id, $0.label) }, uniquingKeysWith: { first, _ in first })
        return first.map { labels[$0] ?? "an unlisted hand" }.sorted().joined(separator: " + ")
    }

    private static let lastHandKey = "lastAttributedHandId"

    static func remember(_ handId: String, defaults: UserDefaults = .standard) {
        defaults.set(handId, forKey: lastHandKey)
    }

    /// The hand the attribute shortcut uses: the last one chosen, while it is still in the project's list.
    static func lastHand(in hands: [InspectorHands.ListedHand], defaults: UserDefaults = .standard) -> InspectorHands.ListedHand? {
        defaults.string(forKey: lastHandKey).flatMap { id in hands.first { $0.id == id } }
    }
}
