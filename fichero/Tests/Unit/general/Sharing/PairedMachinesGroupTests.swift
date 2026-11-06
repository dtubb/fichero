//
//  PairedMachinesGroupTests.swift
//  FicheroTests
//
//  sharing.guest.machines-group / sharing.guest.empty-state-says-how-to-pair (#6360): the Macs this device paired with are
//  one list, kept across a relaunch, one row per host, and the empty group says how to pair.
//

@testable import Fichero
import Foundation
import Testing

struct PairedMachinesGroupTests {
    private func freshDefaults() -> UserDefaults {
        let name = "PairedMachinesGroupTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        defaults.removePersistentDomain(forName: name)
        return defaults
    }

    @Test func aPairingAddsTheHostAndTheLibraryItGave() {
        let defaults = freshDefaults()
        PairedMachineStore.record(apiRoot: URL(string: "https://studio.local:8765")!, library: "/Volumes/Archive/Isthima GHG", in: defaults)
        let rows = PairedMachineStore.load(from: defaults)
        #expect(rows.count == 1)
        #expect(rows[0].name == "studio.local")
        #expect(rows[0].libraries == ["/Volumes/Archive/Isthima GHG"])
    }

    @Test func aSecondPairingWithTheSameHostIsOneRowWithBothLibraries() {
        let defaults = freshDefaults()
        let host = URL(string: "https://studio.local:8765")!
        PairedMachineStore.record(apiRoot: host, library: "/a", in: defaults)
        PairedMachineStore.record(apiRoot: host, library: "/b", in: defaults)
        PairedMachineStore.record(apiRoot: host, library: "/a", in: defaults)
        #expect(PairedMachineStore.load(from: defaults).map(\.libraries) == [["/a", "/b"]])
    }

    @Test func noPairedMacIsNoRowsAndTheEmptyStateSaysHowToPair() {
        #expect(PairedMachineStore.load(from: freshDefaults()).isEmpty)
        #expect(PairedMachinesEmptyView.sentence.contains("File › Connect to Library…"))
        #expect(PairedMachinesEmptyView.sentence.contains("pairing link"))
    }
}
