//
//  HostSharedMarkTests.swift
//  FicheroTests
//
//  sharing.sidebar.host-mark (#5738): the host's project carries a shared mark while Sharing is on.
//  See docs/contributor_manual/specs/transport/library-sharing.md.
//

@testable import Fichero
import Testing

struct HostSharedMarkTests {
    @Test func theHostsOwnProjectIsMarkedOnlyWhileSharingIsOn() {
        #expect(SharedMark.showsOnHost(hostingEnabled: true, isLocal: true))
        #expect(!SharedMark.showsOnHost(hostingEnabled: false, isLocal: true))
    }

    @Test func aGuestsRemoteProjectIsNotTheHostsMark() {
        #expect(!SharedMark.showsOnHost(hostingEnabled: true, isLocal: false))
    }

    @Test func aDeviceInTheInspectorReadsPersonOnDevice() {
        let named = PairedDeviceRecord(
            id: "d1", name: "Alice's Mac", userId: "u1", createdAt: .distantPast, lastSeen: .distantPast,
            expiresAt: .distantFuture, revoked: false, username: "alice")
        #expect(named.inspectorLabel == "alice on Alice's Mac")
    }

    @Test func aDeviceFromAnOlderEngineKeepsItsNameAlone() {
        let unnamed = PairedDeviceRecord(
            id: "d2", name: "Old iPad", userId: "u1", createdAt: .distantPast, lastSeen: .distantPast,
            expiresAt: .distantFuture, revoked: false)
        #expect(unnamed.inspectorLabel == "Old iPad")
    }
}
