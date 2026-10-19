//
//  ActivityReconnectTests.swift
//  FicheroTests
//
//  `activity.reconnects-after-engine-restart` (owner, 2026-10-19 20:14): Activity could not load after Sharing was turned on and
//  never came back, with the raw text "NIOCore.IOError error 1". The failure is said in words, read again with a growing wait, and
//  the run list is read again when the engine answers.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
struct ActivityReconnectTests {
    private let socketError = NSError(domain: "NIOCore.IOError", code: 1)

    private func store() -> ActivityStore {
        let client = FicheroClient(baseURL: URL(string: "https://127.0.0.1:8765")!, libraryPath: "/tmp/ActivityReconnectTests.fichero")
        return ActivityStore(service: ActivityService(ficheroClient: client))
    }

    @Test func aSocketErrorIsTheEngineNotBeingThereAndTheBannerSaysSoInWords() {
        #expect(AccessError.classify(socketError) == .engineUnreachable)
        let message = ActivityStore.runLoadFailureMessage(libraryName: "", error: socketError)
        #expect(message == "Couldn't load activity: the engine could not be reached")
        #expect(!message.contains("NIO"))
    }

    @Test func theWaitGrowsAfterEachFailedReadAndStopsAtThirtySeconds() {
        let waits = (0...7).map { ActivityStore.pollInterval(afterFailures: $0) }
        #expect(waits == [.seconds(2), .seconds(4), .seconds(8), .seconds(16), .seconds(30), .seconds(30), .seconds(30), .seconds(30)])
    }

    @Test func theRunListReloadsWhenTheEngineAnswersAgain() {
        let store = store()
        let before = store.refreshToken
        store.jobsPollFailed(socketError)
        store.jobsPollFailed(socketError)
        #expect(store.jobsPollFailures == 2)
        #expect(store.refreshToken == before, "no reload while the engine is away")
        store.jobsPollSucceeded()
        #expect(store.jobsPollFailures == 0)
        #expect(store.refreshToken == before + 1, "one reload when it answers")
        store.jobsPollSucceeded()
        #expect(store.refreshToken == before + 1, "a read that never failed reloads nothing")
    }

    @Test func aRefusalIsNotCountedAsTheEngineBeingAway() {
        let store = store()
        store.jobsPollFailed(AccessError.unauthenticated)
        #expect(store.jobsPollFailures == 0)
    }

    @Test func eachFailedReadReadsTheEndpointAgain() {
        let store = store()
        var resolved = 0
        store.reresolveEndpoint = { resolved += 1 }
        store.jobsPollFailed(socketError)
        store.jobsPollFailed(socketError)
        #expect(resolved == 2, "a retry dials the endpoint as the engine config says now, not the first connect's")
        store.jobsPollFailed(AccessError.unauthenticated)
        #expect(resolved == 2, "a refusal is not the engine being away")
    }
}
