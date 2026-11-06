//
//  SharingFollowsTheNetworkTests.swift
//  FicheroTests
//
//  t52 (owner live test 2026-11-06): the listener follows the Mac's address: the app restarts its own engine once
//  when health says the address changed.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
struct SharingFollowsTheNetworkTests {
    @Test func aChangedAddressOnTheLocalEngineRestartsIt() {
        #expect(SharingAddressFollower.shouldRestart(changed: true, engineIsLocal: true, now: Date(), last: nil,
                                                     restarting: false))
    }

    @Test func aRemoteEngineOrNoChangeNeverRestarts() {
        #expect(!SharingAddressFollower.shouldRestart(changed: true, engineIsLocal: false, now: Date(), last: nil,
                                                      restarting: false))
        #expect(!SharingAddressFollower.shouldRestart(changed: false, engineIsLocal: true, now: Date(), last: nil,
                                                      restarting: false))
    }

    @Test func atMostOneRestartAMinute() {
        let now = Date()
        #expect(!SharingAddressFollower.shouldRestart(changed: true, engineIsLocal: true, now: now,
                                                      last: now.addingTimeInterval(-10), restarting: false))
        #expect(SharingAddressFollower.shouldRestart(changed: true, engineIsLocal: true, now: now,
                                                     last: now.addingTimeInterval(-61), restarting: false))
        #expect(!SharingAddressFollower.shouldRestart(changed: true, engineIsLocal: true, now: now, last: nil,
                                                      restarting: true))
    }
}
