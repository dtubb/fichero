//
//  ListSelectionScrollPolicyTests.swift
//  FicheroTests
//
//  Daniel, 2026-09-02, live on 2026.09.01.2:
//   · "⌥⇧-deselect works but sometimes the visible scroll position jumps —
//      deselect item 19 and the view jumps to item 7."
//   · "selecting anything takes longer than it should."
//
//  Both come out of ONE watcher: list mode scrolled to the primary row on
//  EVERY selection change. `ListSelectionScrollPolicy` is the rule it now
//  asks first; these are its cases plus the source guard that the list
//  actually consults it.
//

@testable import Fichero
import Foundation
import Testing

@Suite("Deselection never scrolls the list")
struct ListSelectionScrollPolicyTests {

    // MARK: - The reported defect

    @Test("removing a row from the selection never moves the viewport")
    func deselectDoesNotScroll() {
        // Rows 1…19 selected; ⌥⇧-click drops 19. The primary becomes an
        // EARLIER row, and the old watcher animated all the way up to it.
        let previous = Set((1...19).map { "doc-\($0)" })
        let next = previous.subtracting(["doc-19"])

        #expect(
            ListSelectionScrollPolicy.shouldScroll(
                isUserDriven: true,
                previous: previous,
                next: next,
                primary: "doc-7"
            ) == false
        )
        // Even attributed to no live event, a pure narrowing still declines:
        // "deselection must never scroll" is the rule, not a side effect of
        // how the change was attributed.
        #expect(
            ListSelectionScrollPolicy.shouldScroll(
                isUserDriven: false,
                previous: previous,
                next: next,
                primary: "doc-7"
            ) == false
        )
    }

    @Test("clearing the selection has nothing to scroll to")
    func clearDoesNotScroll() {
        #expect(
            ListSelectionScrollPolicy.shouldScroll(
                isUserDriven: true,
                previous: ["doc-1", "doc-2"],
                next: [],
                primary: nil
            ) == false
        )
    }

    // MARK: - The click cost

    @Test("a click never pays for a scroll — the row is already on screen")
    func userClickDoesNotScroll() {
        #expect(
            ListSelectionScrollPolicy.shouldScroll(
                isUserDriven: true,
                previous: ["doc-1"],
                next: ["doc-9"],
                primary: "doc-9"
            ) == false
        )
    }

    @Test("⇧-extending from the primary keeps the viewport put")
    func extendingAroundThePrimaryDoesNotScroll() {
        // The primary was already selected: the user is building a range
        // outward from where they are looking.
        #expect(
            ListSelectionScrollPolicy.shouldScroll(
                isUserDriven: false,
                previous: ["doc-3"],
                next: ["doc-3", "doc-4", "doc-5"],
                primary: "doc-3"
            ) == false
        )
    }

    // MARK: - The case the watcher exists for (#929)

    @Test("a selection written from elsewhere still scrolls into view")
    func programmaticSelectionScrolls() {
        // The PDF preview scrolled to a new page and wrote the selection. The
        // row may be far off screen and the user has no other way to know.
        #expect(
            ListSelectionScrollPolicy.shouldScroll(
                isUserDriven: false,
                previous: ["doc-1"],
                next: ["doc-400"],
                primary: "doc-400"
            )
        )
    }

    @Test("a restored launch selection scrolls into view")
    func restoredSelectionScrolls() {
        #expect(
            ListSelectionScrollPolicy.shouldScroll(
                isUserDriven: false,
                previous: [],
                next: ["doc-88"],
                primary: "doc-88"
            )
        )
    }

    // MARK: - The list actually asks

    @Test("list mode consults the policy instead of scrolling unconditionally")
    func listViewConsultsThePolicy() throws {
        let list = try AppSource.text("Views/Library/ViewModes/List/LibraryView+ListView.swift")
        #expect(list.contains("ListSelectionScrollPolicy.shouldScroll("),
                "the selection watcher must ask the policy before moving the viewport")
        #expect(list.contains("isUserDriven: selectionChangeIsUserDriven"),
                "the policy needs the SAME user-driven probe the Table uses")
        #expect(!list.contains(".onChange(of: selection) { _, _ in"),
                "the watcher must read the OLD and NEW selection — a narrowing is only "
                    + "visible as a difference between them")
    }
}
