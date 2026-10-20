//
//  ActivityStreamRecoveryTests.swift
//  FicheroTests
//
//  activity.stream-reconnects-after-a-sharing-switch (#5912): the live stream comes back by itself after the engine
//  restarts, re-reads the endpoint on each failed attempt, reads the run list again once, and says "Reconnecting".
//  See docs/contributor_manual/specs/ui/activity-and-automatic-work.md.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
struct ActivityStreamRecoveryTests {
    private func service() -> ActivityStreamService {
        let client = FicheroClient(baseURL: URL(string: "https://127.0.0.1:8765")!, libraryPath: "/tmp/ActivityStreamRecoveryTests.fichero")
        return ActivityStreamService(activityService: ActivityService(ficheroClient: client))
    }

    @Test func eachDropReadsTheEndpointAgain() {
        let service = service()
        var resolved = 0
        service.onDrop = { resolved += 1 }
        service.noteDrop()
        service.noteDrop()
        #expect(resolved == 2)
    }

    @Test func theFirstConnectAfterADropReadsTheRunListOnceMore() {
        let service = service()
        var resynced = 0
        service.onReconnected = { resynced += 1 }
        service.noteDrop()
        service.noteConnected()
        service.noteConnected()  // a second connect with no drop between is a rotation
        #expect(resynced == 1)
    }

    @Test func theVeryFirstConnectOrACleanRotationReadsNothingMore() {
        let service = service()
        var resynced = 0
        service.onReconnected = { resynced += 1 }
        service.noteConnected()
        service.noteConnected()
        #expect(resynced == 0)
    }

    @Test func aDropBeforeAnyConnectIsStillRecoveredFrom() {
        let service = service()
        var resynced = 0
        service.onReconnected = { resynced += 1 }
        service.noteDrop()  // the engine was restarting at launch
        service.noteConnected()
        #expect(resynced == 1)
    }

    @Test func thePillKeepsItsPlainDefaultForEveryOtherScreen() {
        #expect(LiveUpdatesPausedPill().message == "Live updates paused")
    }

    @Test func activityPillSaysReconnectingWhileTheStreamRetriesItself() {
        let client = FicheroClient(baseURL: URL(string: "https://127.0.0.1:8765")!, libraryPath: "/tmp/ActivityStreamRecoveryTests.fichero")
        let store = ActivityStore(service: ActivityService(ficheroClient: client))
        #expect(store.livePillMessage == "Reconnecting to the engine…")
    }

    @Test func theStoreWiresTheStreamToItsEndpointAndItsRunList() {
        let client = FicheroClient(baseURL: URL(string: "https://127.0.0.1:8765")!, libraryPath: "/tmp/ActivityStreamRecoveryTests.fichero")
        let store = ActivityStore(service: ActivityService(ficheroClient: client))
        var resolved = 0
        store.reresolveEndpoint = { resolved += 1 }
        store.wireStreamRecovery()
        let before = store.refreshToken
        store.streamServiceForTesting.noteDrop()
        store.streamServiceForTesting.noteConnected()
        #expect(resolved == 1)
        #expect(store.refreshToken == before + 1)
    }
}
