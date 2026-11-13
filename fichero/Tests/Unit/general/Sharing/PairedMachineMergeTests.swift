import Foundation
@testable import Fichero
import Testing

/// A shared Mac shows once, under the name the person gave it, listing only the libraries it has open
/// (`sharing.guest.one-section-per-mac`, #6556).
@MainActor
struct PairedMachineMergeTests {
    private static let local = "https://studio.local:8766"
    private static let tailnet = "https://studio.tail1234.ts.net:8766"

    @Test func twoAddressesOfOneMacAreOneSection() {
        let machines = [
            PairedMachine(id: Self.local, name: "studio.local", libraries: ["/A", "/B"], addresses: [Self.tailnet]),
            PairedMachine(id: Self.tailnet, name: "studio.tail1234.ts.net", libraries: ["/B", "/C"])
        ]
        let sections = SharedMachineSections.sections(machines)
        #expect(sections.count == 1)
        #expect(sections.first?.rows == [.library("/A"), .library("/B"), .library("/C")])
    }

    @Test func macsWithNoAddressInCommonStayApart() {
        let machines = [
            PairedMachine(id: Self.local, name: "studio.local", libraries: ["/A"]),
            PairedMachine(id: "https://other.local:8766", name: "other.local", libraries: ["/B"])
        ]
        #expect(SharedMachineSections.sections(machines).count == 2)
    }

    @Test func theSectionIsTitledByThePersonsName() {
        let machine = PairedMachine(id: Self.local, name: "studio.local", libraries: ["/A"], customName: "Pro")
        #expect(machine.shownName == "Pro")
        #expect(PairedMachine(id: Self.local, name: "studio.local", libraries: [], customName: "  ").shownName == "studio.local")
    }

    @Test func aHostThatAnsweredListsOnlyItsOpenLibraries() {
        let machines = [PairedMachine(id: Self.local, name: "studio.local", libraries: ["/A", "/B", "/C"])]
        let sections = SharedMachineSections.sections(machines, openOnHost: [Self.local: ["/B"]])
        #expect(sections.first?.rows == [.library("/B")])
    }

    @Test func aHostThatHasNotAnsweredKeepsEveryLibrary() {
        let machines = [PairedMachine(id: Self.local, name: "studio.local", libraries: ["/A", "/B"])]
        #expect(SharedMachineSections.sections(machines).first?.rows == [.library("/A"), .library("/B")])
    }

    @Test func aHostWithNoneOfItsSharedLibrariesOpenSaysSo() {
        let machines = [PairedMachine(id: Self.local, name: "studio.local", libraries: ["/A"], customName: "Pro")]
        let rows = SharedMachineSections.sections(machines, openOnHost: [Self.local: []]).first?.rows
        #expect(rows == [.nothingShared("Pro has none of its shared projects open")])
    }

    @Test func aRowSavedBeforeAddressesDecodesWithNone() throws {
        let old = #"[{"id":"https://studio.local:8766","name":"studio.local","libraries":["/A"]}]"#
        let rows = try JSONDecoder().decode([PairedMachine].self, from: Data(old.utf8))
        #expect(rows.first?.addresses == [])
        #expect(rows.first?.customName == nil)
    }

    @Test func pairingOverAnotherAddressLandsOnTheSameRow() throws {
        let defaults = try #require(UserDefaults(suiteName: "PairedMachineMergeTests"))
        defaults.removePersistentDomain(forName: "PairedMachineMergeTests")
        defer { defaults.removePersistentDomain(forName: "PairedMachineMergeTests") }
        let local = try #require(URL(string: Self.local))
        let tailnet = try #require(URL(string: Self.tailnet))
        PairedMachineStore.record(apiRoot: local, library: "/A", addresses: [Self.tailnet], in: defaults)
        PairedMachineStore.record(apiRoot: tailnet, library: "/B", in: defaults)
        let rows = PairedMachineStore.load(from: defaults)
        #expect(rows.count == 1)
        #expect(rows.first?.libraries == ["/A", "/B"])
    }

    @Test func theHostsOwnAddressesAreAddedOnce() {
        let merged = SharedRowAvailability.addresses(
            known: [Self.tailnet], listed: [Self.local, Self.tailnet, "https://10.0.0.4:8766"], id: Self.local
        )
        #expect(merged == [Self.tailnet, "https://10.0.0.4:8766"])
    }
}
