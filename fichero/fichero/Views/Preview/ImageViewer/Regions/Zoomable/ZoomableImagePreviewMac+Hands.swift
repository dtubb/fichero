#if os(macOS)
import SwiftUI

/// The menu bar's hand verbs on the Preview's selection (#5161; `source.hand.assign-from-every-surface`): the same
/// `HandAssignment` calls the row menu sends, each one audited action, one ⌘Z.
extension ZoomableImagePreview {
    /// ⌃⌘H: the selection takes the hand last chosen from any surface; says so when there is none.
    func attributeSelectedToLastHand() {
        runHandVerb { ids, hands, _ in
            guard let last = HandAssignment.lastHand(in: hands) else { return nil }
            return HandAssignment.attribute(handId: last.id, segmentIds: ids)
        }
    }

    /// Remove Hand: every live attribution on the selection is withdrawn.
    func removeHandFromSelected() {
        runHandVerb { ids, _, attributions in HandAssignment.remove(selection: ids, attributions: attributions) }
    }

    private func runHandVerb(
        _ plan: @escaping ([String], [InspectorHands.ListedHand], [String: [InspectorHands.Attribution]]) -> HandAssignment.Call?
    ) {
        guard let documentId, let segmentService, let actionsService = actionStore?.actionsService else { return }
        let ids = selectedSegments(documentId).map(\.id), steps = windowSteps
        let service = HandService(client: segmentService.client)
        Task {
            let hands = (try? await service.hands()) ?? []
            var attributions: [String: [InspectorHands.Attribution]] = [:]
            for id in ids { attributions[id] = (try? await service.attributions(segmentId: id)) ?? [] }
            guard let call = plan(ids, hands, attributions) else { return }
            _ = try? await AuditedAction.run(
                call.action, params: call.params, actionName: call.name, actionsService: actionsService, steps: steps
            )
        }
    }
}
#endif
