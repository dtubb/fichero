//
//  LibraryOpeningProgressTests.swift
//  FicheroTests
//
//  #6430: a library still opening says which it is and where it stands.
//

@testable import Fichero
import Foundation
import Testing

struct LibraryOpeningProgressTests {
    private let ids = (0..<4).map { _ in UUID() }

    @Test func aWaitingLibrarySaysItsPlaceInTheOrder() {
        #expect(LibraryOpeningProgress.message(name: "Marshall", id: ids[1], order: ids) == "Opening Marshall (2 of 4)…")
    }

    @Test func theFrontLibraryIsFirst() {
        #expect(LibraryOpeningProgress.message(name: "Front", id: ids[0], order: ids) == "Opening Front (1 of 4)…")
    }

    @Test func oneLibraryHasNothingToCountAndAStrangerIsNotNamed() {
        #expect(LibraryOpeningProgress.message(name: "Only", id: ids[0], order: [ids[0]]) == nil)
        #expect(LibraryOpeningProgress.message(name: "Other", id: UUID(), order: ids) == nil)
    }
}
