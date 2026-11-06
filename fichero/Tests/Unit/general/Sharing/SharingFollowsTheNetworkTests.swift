//
//  SharingFollowsTheNetworkTests.swift
//  FicheroTests
//
//  t52/t55 (owner live test 2026-11-06): the listener follows the Mac's address (the app restarts its own engine once
//  when health says the address changed), and the app makes the Tailscale forward the sandboxed engine cannot.
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

#if os(macOS)
    @Test func theTailnetAddressIsReadFromARunningTailscale() {
        let running = Data(#"{"BackendState":"Running","Self":{"DNSName":"pro.tail1234.ts.net."}}"#.utf8)
        let stopped = Data(#"{"BackendState":"Stopped","Self":{"DNSName":"pro.tail1234.ts.net."}}"#.utf8)
        #expect(TailnetForwardMaker.tailnetURL(fromStatus: running) == "https://pro.tail1234.ts.net")
        #expect(TailnetForwardMaker.tailnetURL(fromStatus: stopped) == nil)
    }

    @Test func theForwardIsReadAsTheEngineReadsIt() {
        let ours = Data(#"""
        {"TCP":{"8765":{"HTTPS":true}},"Web":{"pro.tail1234.ts.net:8765":{"Handlers":{"/":{"Proxy":"https+insecure://127.0.0.1:8765"}}}}}
        """#.utf8)
        let raw = Data(#"{"TCP":{"8765":{"TCPForward":"127.0.0.1:8765"}}}"#.utf8)
        #expect(TailnetForwardMaker.forwardTarget(fromServeStatus: ours, port: 8765) == TailnetForwardMaker.wanted(port: 8765))
        #expect(TailnetForwardMaker.forwardTarget(fromServeStatus: raw, port: 8765) == "tcp://127.0.0.1:8765")
        #expect(TailnetForwardMaker.forwardTarget(fromServeStatus: Data("{}".utf8), port: 8765) == nil)
    }
#endif
}
