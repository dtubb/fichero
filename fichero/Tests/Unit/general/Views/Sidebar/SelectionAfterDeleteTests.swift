//
//  SelectionAfterDeleteTests.swift
//  FicheroTests
//
//  sidebar-crud (#4805): the Finder rule for where selection goes after a delete.
//

@testable import Fichero
import Testing

struct SelectionAfterDeleteTests {
    @Test func nextSiblingWins() {
        #expect(selectionAfterDelete(deleted: "b", siblings: ["a", "b", "c"], parent: "p") == "c")
    }

    @Test func lastRowFallsBackToPreviousSibling() {
        #expect(selectionAfterDelete(deleted: "c", siblings: ["a", "b", "c"], parent: "p") == "b")
    }

    @Test func onlyChildFallsBackToParent() {
        #expect(selectionAfterDelete(deleted: "a", siblings: ["a"], parent: "p") == "p")
    }

    @Test func noSiblingsNoParentClears() {
        #expect(selectionAfterDelete(deleted: "a", siblings: ["a"], parent: nil) == nil)
    }

    @Test func unknownRowFallsBackToParent() {
        #expect(selectionAfterDelete(deleted: "x", siblings: [], parent: "p") == "p")
    }
}
