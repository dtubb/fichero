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
    /// The host-state read in these tests: no network, no answer (#6556 added the read; unit tests never dial a host).
    static let noHostState: (URL) async -> SharedRowAvailability.HostState = { _ in .init() }

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
            PairedMachineStore.save(savedMachines)
            manager.greyedSharedRows = []
            manager.hostRowsLastAsked = [:]
        }
        manager.hostRowsLastAsked = [:]
        manager.pairedMachines = [PairedMachine(id: host, name: "studio.local", libraries: ["/A", "/B"])]
        manager.greyedSharedRows = [SharedRowAvailability.key(host: host, library: "/A")]
        await manager.checkSharedRows(now: Date(), read: { _ in ["/A"] }, readState: Self.noHostState)
        #expect(manager.greyedSharedRows == [SharedRowAvailability.key(host: host, library: "/B")])

        manager.hostRowsLastAsked = [:]
        await manager.checkSharedRows(now: Date(), read: { _ in nil }, readState: Self.noHostState)
        #expect(manager.greyedSharedRows == [SharedRowAvailability.key(host: host, library: "/B")])  // unchanged
    }

    @Test func aLibraryTheHostListsSincePairingAppearsAndADroppedOneStays() async {
        #expect(SharedRowAvailability.merged(known: ["/A"], accessible: ["/A", "/C"]) == ["/A", "/C"])
        #expect(SharedRowAvailability.merged(known: ["/A", "/B"], accessible: ["/A"]) == ["/A", "/B"])
        let manager = LibraryManager.shared
        let savedMachines = manager.pairedMachines
        defer {
            manager.pairedMachines = savedMachines
            PairedMachineStore.save(savedMachines)
            manager.greyedSharedRows = []
            manager.hostRowsLastAsked = [:]
        }
        manager.hostRowsLastAsked = [:]
        manager.pairedMachines = [PairedMachine(id: host, name: "studio.local", libraries: ["/A"])]
        await manager.checkSharedRows(now: Date(), read: { _ in ["/A", "/C"] }, readState: Self.noHostState)
        #expect(manager.pairedMachines.first?.libraries == ["/A", "/C"])
        #expect(PairedMachineStore.load().first { $0.id == host }?.libraries == ["/A", "/C"])
        manager.hostRowsLastAsked = [:]
        await manager.checkSharedRows(now: Date(), read: { _ in nil }, readState: Self.noHostState)  // a failed read changes no list
        #expect(manager.pairedMachines.first?.libraries == ["/A", "/C"])
    }

    /// The connection popover's rows read these (#6434): an answer is connected with a time, a failed read is asleep.
    @Test func checkingRecordsWhoAnsweredAndAskHostAgainIgnoresTheThrottle() async {
        let manager = LibraryManager.shared
        let savedMachines = manager.pairedMachines
        defer {
            manager.pairedMachines = savedMachines
            PairedMachineStore.save(savedMachines)
            manager.greyedSharedRows = []
            manager.hostRowsLastAsked = [:]
            manager.hostStates = [:]
            manager.hostLastAnswered = [:]
        }
        manager.hostRowsLastAsked = [:]
        manager.hostStates = [:]
        manager.hostLastAnswered = [:]
        manager.pairedMachines = [PairedMachine(id: host, name: "studio.local", libraries: ["/A"])]
        let answered = Date(timeIntervalSince1970: 5_000)
        await manager.checkSharedRows(now: answered, read: { _ in ["/A"] }, readState: Self.noHostState)
        #expect(manager.hostStates[host] == .connected)
        #expect(manager.hostLastAnswered[host] == answered)

        // Asked a second ago: the throttle skips it, so nothing is read and the state stays.
        await manager.checkSharedRows(now: answered.addingTimeInterval(1), read: { _ in nil }, readState: Self.noHostState)
        #expect(manager.hostStates[host] == .connected)

        // Past the throttle a failed read is asleep and keeps the last time it answered.
        await manager.checkSharedRows(now: answered.addingTimeInterval(61), read: { _ in nil }, readState: Self.noHostState)
        #expect(manager.hostStates[host] == .asleep)
        #expect(manager.hostLastAnswered[host] == answered)

        // Reconnect clears the throttle for that host, so the next check asks at once.
        manager.hostRowsLastAsked[host] = Date()
        await manager.askHostAgain(host, read: { _ in ["/A"] }, readState: Self.noHostState)
        #expect(manager.hostStates[host] == .connected)
    }

    @Test func aTailscaleNameIsReadWithNoPinAndAnOwnCertificateNeedsOne() throws {
        let tailnet = try #require(URL(string: "https://studio.tail1234.ts.net:8765"))
        let own = try #require(URL(string: "https://studio.local:8765"))
        #expect(SharedRowAvailability.readTrust(tailnet, stored: nil) == .init(pin: nil))  // the Tailscale name keeps no pin (#6433)
        #expect(SharedRowAvailability.readTrust(own, stored: nil) == nil)
        let pin = Data("spki".utf8).base64EncodedString()
        #expect(SharedRowAvailability.readTrust(own, stored: pin) == .init(pin: pin))
    }

    @Test func aHostWithNoStoredPinIsNotAskedAtAll() async {
        // No pin, no connection: never the local engine, never the system trust store.
        let unknown = URL(string: "https://never-paired-\(UUID().uuidString.lowercased()).invalid:8765")!
        #expect(await SharedRowAvailability.readFromHost(unknown) == nil)
    }
}
