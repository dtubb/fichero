@testable import Fichero
import Testing

// #145 (2026-08-09): ⇧/⌘ clicks on a draggable row's NAME never reach
// List(selection:), so the tap fallback builds the proposal itself — same
// Finder semantics, same one commit seam. These pin the pure builder.
@Suite("sidebarFallbackProposal — Finder semantics for label clicks")
struct SidebarFallbackProposalTests {
    private let rows: [SidebarDestination] = [
        .document("a"), .document("b"), .document("c"), .document("d")
    ]

    @Test("plain click selects the clicked row alone")
    func plainClick() {
        let out = sidebarFallbackProposal(
            clicked: .document("c"), current: [.document("a")],
            anchor: .document("a"), orderedSiblings: rows,
            modifiers: (shift: false, command: false)
        )
        #expect(out == [.document("c")])
    }

    @Test("shift extends the contiguous range from the anchor, both directions")
    func shiftRange() {
        let down = sidebarFallbackProposal(
            clicked: .document("c"), current: [.document("a")],
            anchor: .document("a"), orderedSiblings: rows,
            modifiers: (shift: true, command: false)
        )
        #expect(down == [.document("a"), .document("b"), .document("c")])
        let up = sidebarFallbackProposal(
            clicked: .document("a"), current: [.document("c")],
            anchor: .document("c"), orderedSiblings: rows,
            modifiers: (shift: true, command: false)
        )
        #expect(up == [.document("a"), .document("b"), .document("c")])
    }

    @Test("shift with an anchor outside the sibling list still ADDS the row")
    func shiftCrossSectionUnions() {
        let out = sidebarFallbackProposal(
            clicked: .document("d"), current: [.search("s1")],
            anchor: .search("s1"), orderedSiblings: rows,
            modifiers: (shift: true, command: false)
        )
        #expect(out == [.search("s1"), .document("d")])
    }

    @Test("command toggles membership without touching the rest")
    func commandToggles() {
        let added = sidebarFallbackProposal(
            clicked: .document("b"), current: [.document("a")],
            anchor: .document("a"), orderedSiblings: rows,
            modifiers: (shift: false, command: true)
        )
        #expect(added == [.document("a"), .document("b")])
        let removed = sidebarFallbackProposal(
            clicked: .document("a"), current: [.document("a"), .document("b")],
            anchor: .document("a"), orderedSiblings: rows,
            modifiers: (shift: false, command: true)
        )
        #expect(removed == [.document("b")])
    }
}
