import Foundation
@testable import Fichero
import Testing

/// #5652 slice 4, group 4: Edit › Proposed Document ▸ renders the Items list's own menu over proposed documents
/// (`ProposedDocumentsMenu`), and Edit › Direction ▸ the Items list's and the Inspector's own `SourceDirectionMenu`,
/// on the focused Items list's selection. What breaks without these: the bar offering to answer a proposal the
/// selection does not name, stating the direction of several sources at once, or answering through a second path.
@MainActor
@Suite("Proposed documents and a source's direction in Edit (#5652 slice 4)")
struct ProposalAndDirectionMenuTests {
    private let page = Document(id: "p1", docType: .file, fileType: .image, name: "0970.jpg")
    private let folder = Document(id: "f1", docType: .folder, name: "Letters")

    @Test("Proposed Document ▸ needs the selection to name a proposal, and says so")
    func proposalReason() {
        #expect(ItemVerbs.proposalReason(nil) == "Select a proposed document, or one of its pages, in Items")
        var target = ItemVerbsTarget(ids: ["p1"], documents: [page])
        #expect(ItemVerbs.proposalReason(target) != nil)
        target.proposals = ProposalVerbs(target: .init(documents: [], pageId: "p1")) { _ in }
        #expect(ItemVerbs.proposalReason(target) == nil)
    }

    @Test("an answer from the bar reaches the Items list's one answer path")
    func answerReachesTheList() {
        var answers: [ProposalAnswer] = []
        let verbs = ProposalVerbs(target: .init(documents: [], pageId: nil)) { answers.append($0) }
        verbs.answer(.accept)
        verbs.answer(.split(pageId: "p2"))
        #expect(answers == [.accept, .split(pageId: "p2")])
    }

    @Test("Direction ▸ acts on one folder, document or page, and says why otherwise")
    func directionReason() {
        #expect(ItemVerbs.directionReason(nil) == ItemVerbs.nothingSelected)
        let two = ItemVerbsTarget(ids: ["p1", "f1"], documents: [page, folder])
        #expect(ItemVerbs.directionReason(two) == "Select one folder, document or page")
        var one = ItemVerbsTarget(ids: ["f1"], documents: [folder])
        #expect(ItemVerbs.directionReason(one) == "Select it in Items to state its direction")
        one.direction = DirectionVerbs(nodeId: "f1", actionsService: nil, steps: nil)
        #expect(ItemVerbs.directionReason(one) == nil)
        #expect(SourceDirectionMenu(nodeId: "f1", actionsService: nil).title == ItemVerbs.directionTitle)
    }

    @Test("the target compares by the proposals and the source it names, so the same selection does not republish")
    func equality() {
        var lhs = ItemVerbsTarget(ids: ["f1"], documents: [folder])
        var rhs = lhs
        lhs.direction = DirectionVerbs(nodeId: "f1", actionsService: nil, steps: nil)
        rhs.direction = DirectionVerbs(nodeId: "f1", actionsService: nil, steps: nil)
        #expect(lhs == rhs)
        rhs.direction = DirectionVerbs(nodeId: "f2", actionsService: nil, steps: nil)
        #expect(lhs != rhs)
        rhs.direction = lhs.direction
        rhs.proposals = ProposalVerbs(target: .init(documents: [], pageId: nil)) { _ in }
        #expect(lhs != rhs)
    }
}
