import SwiftUI

// MARK: - Proposed documents and a source's direction, in the menu bar (#5652 slice 4, group 4)

// The Items list's menu over proposed documents (`ProposedDocumentsMenu`: Accept, Reject and, for one, the page
// adjustments) and a source's Direction ▸ (`SourceDirectionMenu`, also the Inspector's) are each ONE component; Edit
// renders them on the focused Items list's selection, through `ItemVerbsTarget`, disabled with a reason under them
// when the selection names no proposal or more than one source.

/// Proposed documents the selection names, with the one way they are answered (`LibraryView.answerProposals`).
struct ProposalVerbs: Equatable {
    let target: LibraryOutlineNode.ProposalTarget
    let answer: @MainActor (ProposalAnswer) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool { lhs.target == rhs.target }
}

/// One source whose direction can be stated: its node, the services the audited action runs through, the window's
/// steps for ⌘Z.
struct DirectionVerbs: Equatable {
    let nodeId: String
    let actionsService: ActionsService?
    let steps: WindowSteps?

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.nodeId == rhs.nodeId && (lhs.actionsService == nil) == (rhs.actionsService == nil)
    }
}

extension ItemVerbs {
    static let proposedTitle = "Proposed Document"
    static let directionTitle = "Direction"

    static func proposalReason(_ target: ItemVerbsTarget?) -> String? {
        target?.proposals == nil ? "Select a proposed document, or one of its pages, in Items" : nil
    }

    static func directionReason(_ target: ItemVerbsTarget?) -> String? {
        guard let target, !target.ids.isEmpty else { return nothingSelected }
        if target.documents.count != 1 || target.ids.count != 1 { return "Select one folder, document or page" }
        return target.direction == nil ? "Select it in Items to state its direction" : nil
    }
}

/// Edit › Proposed Document ▸ and Direction ▸ on the focused selection.
struct FocusedProposalAndDirectionMenus: View {
    @FocusedValue(\.itemVerbs) private var items
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @FocusedValue(\.sidebarSelectionInfo) private var selectionInfo

    var body: some View {
        let target = FocusedItemVerbs.target(items: items, actions: sidebarActions, info: selectionInfo)
        if let proposals = target?.proposals {
            Menu(ItemVerbs.proposedTitle) {
                ProposedDocumentsMenu(target: proposals.target) { proposals.answer($0) }
            }
        } else {
            Menu(ItemVerbs.proposedTitle) {}
                .disabled(true)
            FocusedItemOrganiseButtons.reason(ItemVerbs.proposalReason(target))
        }
        if let direction = target?.direction, ItemVerbs.directionReason(target) == nil {
            SourceDirectionMenu(
                nodeId: direction.nodeId, actionsService: direction.actionsService, steps: direction.steps
            )
        } else {
            Menu(ItemVerbs.directionTitle) {}
                .disabled(true)
            FocusedItemOrganiseButtons.reason(ItemVerbs.directionReason(target))
        }
    }
}
