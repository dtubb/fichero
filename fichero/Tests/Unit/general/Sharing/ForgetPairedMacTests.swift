//
//  ForgetPairedMacTests.swift
//  FicheroTests
//
//  sharing.guest.forget-a-mac (#6662): forgetting a Mac this Mac joined leaves no token, no rows and nothing to dial.
//  See docs/contributor_manual/specs/transport/library-sharing.md.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
struct ForgetPairedMacTests {
    private static let root = URL(string: "https://forget-test.invalid:8765")!

    @Test func forgettingAPairedMacLeavesNoTokenNoRowsAndNothingToDial() throws {
        let host = Self.root.absoluteString
        let manager = LibraryManager.shared
        let savedMachines = manager.pairedMachines
        let savedGone = manager.hostGoneRows
        defer {
            manager.pairedMachines = savedMachines
            PairedMachineStore.save(savedMachines)
            manager.hostGoneRows = savedGone
            AuthTokenMiddleware.clearRemoteToken(hostString: host)
        }
        try PairingService.persistAuthToken("tok", for: Self.root)
        let expiry = Date(timeIntervalSince1970: 2_000_000_000)
        DeviceTokenRenewal.storeExpiry(expiry, host: host)
        PairedMachineStore.record(apiRoot: Self.root, library: "/A")
        manager.pairedMachines = PairedMachineStore.load()
        manager.hostGoneRows = [HostGoneRow(id: UUID(), name: "A", host: "forget-test.invalid")]
        #expect(AuthTokenMiddleware.readRemoteTokenForHost(host) == "tok")

        manager.forgetPairedMachine(host)

        #expect(AuthTokenMiddleware.readRemoteTokenForHost(host) == nil, "no stored token")
        #expect(DeviceTokenRenewal.storedExpiry(host: host) == nil)
        #expect(!manager.pairedMachines.contains { $0.id == host }, "no sidebar section, nothing for the availability poll to dial")
        #expect(!PairedMachineStore.load().contains { $0.id == host }, "gone after a relaunch")
        #expect(manager.hostGoneRows.isEmpty, "no greyed row")
    }

    @Test func forgettingOneMacKeepsTheOther() {
        let manager = LibraryManager.shared
        let saved = manager.pairedMachines
        defer { manager.pairedMachines = saved; PairedMachineStore.save(saved) }
        let first = PairedMachine(id: "https://forget-a.invalid:1", name: "a", libraries: [])
        let second = PairedMachine(id: "https://forget-b.invalid:1", name: "b", libraries: [])
        manager.pairedMachines = [first, second]
        manager.forgetPairedMachine(first.id)
        #expect(manager.pairedMachines == [second])
    }

    @Test func theMenuItemAsksByNameAndConfirmCallsForget() {
        let manager = LibraryManager.shared
        let saved = manager.pairedMachines
        defer { manager.pairedMachines = saved; PairedMachineStore.save(saved) }
        let machine = PairedMachine(id: "https://forget-c.invalid:1", name: "c.invalid", libraries: [], customName: "Pro")
        manager.pairedMachines = [machine]
        let prompt = ForgetMachinePrompt(machine: machine)
        #expect(ForgetMachinePrompt.menuTitle == "Forget This Mac…")
        #expect(prompt.question == "Forget Pro?")
        #expect(ForgetMachinePrompt.message == "Its projects leave your sidebar; you can join again with a new code.")
        prompt.confirm(in: manager)
        #expect(manager.pairedMachines.isEmpty)
    }
}
