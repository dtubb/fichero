//
//  SharingOffGreysRowTests.swift
//  FicheroTests
//
//  sharing.sidebar.off-greys-row (#5739): the guest's row stays, greyed, with one sentence.
//  See docs/contributor_manual/specs/transport/library-sharing.md.
//

@testable import Fichero
import Foundation
import Testing

struct SharingOffGreysRowTests {
    @Test func theSentenceNamesTheHost() {
        let row = HostGoneRow(id: UUID(), name: "Marshall", host: "studio.local")
        #expect(row.sentence == "Not available: sharing is off on studio.local")
    }

    @Test func aHostWithNoNameStillReads() {
        let row = HostGoneRow(id: UUID(), name: "Marshall", host: "")
        #expect(row.sentence == "Not available: sharing is off on the host")
    }

    @MainActor @Test func forgetRemovesOnlyThatRow() {
        let manager = LibraryManager.shared
        let kept = HostGoneRow(id: UUID(), name: "Kept", host: "a")
        let gone = HostGoneRow(id: UUID(), name: "Gone", host: "b")
        manager.hostGoneRows = [kept, gone]
        manager.forgetHostGoneRow(id: gone.id)
        #expect(manager.hostGoneRows == [kept])
        manager.hostGoneRows = []
    }
}
