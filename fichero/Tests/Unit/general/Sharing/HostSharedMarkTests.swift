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
}
