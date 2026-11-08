//
//  SharedRowAvailabilityTests.swift
//  FicheroTests
//
//  sharing.marks.off-greys-row (#5739, #6360): a Shared Libraries row greys only when its host ANSWERED and no longer lists
//  the library; a failed read greys nothing; a host is asked at most once a minute.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
struct SharedRowAvailabilityTests {
    private let host = "https://studio.local:8765"

    @Test func aLibraryTheHostNoLongerListsIsGreyed() {
        let gone = SharedRowAvailability.unavailable(libraries: ["/A", "/B"], accessible: ["/A"])
        #expect(gone == ["/B"])
    }

    @Test func aFailedReadGreysNothing() {
        #expect(SharedRowAvailability.unavailable(libraries: ["/A"], accessible: nil).isEmpty)
    }

    @Test func anAnswerThatListsEverythingGreysNothing() {
        #expect(SharedRowAvailability.unavailable(libraries: ["/A"], accessible: ["/A", "/Z"]).isEmpty)
    }

    @Test func theHostSpellingOfAnAccentedPathStillMatches() {
        let nfd = "/Archive/Cafe\u{301}"
        let nfc = "/Archive/Caf\u{E9}"
        #expect(SharedRowAvailability.unavailable(libraries: [nfd], accessible: [nfc]).isEmpty)
    }

    @Test func aHostAskedUnderAMinuteAgoIsNotAskedAgain() {
        let now = Date()
        #expect(!SharedRowAvailability.shouldAsk(host: host, now: now, lastAsked: [host: now.addingTimeInterval(-59)]))
        #expect(SharedRowAvailability.shouldAsk(host: host, now: now, lastAsked: [host: now.addingTimeInterval(-60)]))
        #expect(SharedRowAvailability.shouldAsk(host: host, now: now, lastAsked: [:]))
    }

    @Test func checkingGreysTheDroppedRowAndALaterFailedReadChangesNothing() async {
        let manager = LibraryManager.shared
        let savedMachines = manager.pairedMachines
        defer {
            manager.pairedMachines = savedMachines
            manager.greyedSharedRows = []
            manager.hostRowsLastAsked = [:]
        }
        manager.hostRowsLastAsked = [:]
        manager.pairedMachines = [PairedMachine(id: host, name: "studio.local", libraries: ["/A", "/B"])]
        manager.greyedSharedRows = [SharedRowAvailability.key(host: host, library: "/A")]
        await manager.checkSharedRows(now: Date()) { _ in ["/A"] }
        #expect(manager.greyedSharedRows == [SharedRowAvailability.key(host: host, library: "/B")])

        manager.hostRowsLastAsked = [:]
        await manager.checkSharedRows(now: Date()) { _ in nil }
        #expect(manager.greyedSharedRows == [SharedRowAvailability.key(host: host, library: "/B")])  // unchanged
    }

    @Test func aHostWithNoStoredPinIsNotAskedAtAll() async {
        // No pin, no connection: never the local engine, never the system trust store.
        let unknown = URL(string: "https://never-paired-\(UUID().uuidString.lowercased()).invalid:8765")!
        #expect(await SharedRowAvailability.readFromHost(unknown) == nil)
    }
}
