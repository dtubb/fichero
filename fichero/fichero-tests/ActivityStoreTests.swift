//
//  ActivityStoreTests.swift
//  FicheroTests
//
//  Unit tests for ActivityStore (#2448, #2633).  Verifies that activity
//  events, not workflow-definition change events, refresh the browser.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

// MARK: - Helpers

@MainActor
private func makeStore() -> ActivityStore {
    let client = FicheroClient(libraryPath: "/tmp/test.fichero")
    let service = ActivityServiceGenerated(ficheroClient: client)
    return ActivityStore(service: service)
}

private func makeEvent(domain: String, verb: String = "created") throws -> ChangeEvent {
    let payload: [String: Any] = [
        "type": "\(domain).\(verb)",
        "actor": "test"
    ]
    let data = try JSONSerialization.data(withJSONObject: payload)
    return try JSONDecoder().decode(ChangeEvent.self, from: data)
}

// MARK: - ActivityStoreTests

@MainActor
struct ActivityStoreTests {

    // MARK: changeDomains

    @Test("changeDomains is empty because activity refresh uses /activity/stream")
    func changeDomainsAreEmpty() {
        let store = makeStore()
        #expect(store.changeDomains.isEmpty)
    }

    @Test("changeDomains does not contain workflow definitions or unrelated domains")
    func changeDomainExcludesOthers() {
        let store = makeStore()
        #expect(!store.changeDomains.contains("workflow"))
        #expect(!store.changeDomains.contains("document"))
        #expect(!store.changeDomains.contains("entity"))
        #expect(!store.changeDomains.contains("activity"))
    }

    // MARK: apply(_:)

    @Test("workflow change event does not increment refreshToken")
    func workflowChangeEventDoesNotIncrementToken() throws {
        let store = makeStore()
        let before = store.refreshToken
        let event = try makeEvent(domain: "workflow", verb: "created")
        store.apply(event)
        #expect(store.refreshToken == before)
    }

    @Test("applyActivityEvent increments refreshToken once per event")
    func applyActivityEventIncrementsToken() {
        let store = makeStore()
        let before = store.refreshToken
        let event = ActivityItem(
            id: "act-1",
            type: "workflow_started",
            level: "info",
            timestamp: "2026-06-25T12:00:00Z",
            message: "Started",
            threadId: "thread-1"
        )
        store.applyActivityEvent(event)
        #expect(store.refreshToken == before + 1)
    }

    @Test("duplicate activity events each bump refreshToken")
    func duplicateActivityEventsBumpEveryTime() {
        let store = makeStore()
        let event = ActivityItem(
            id: "act-1",
            type: "workflow_completed",
            level: "info",
            timestamp: "2026-06-25T12:00:01Z",
            message: "Completed",
            threadId: "thread-1"
        )
        let first = store.refreshToken
        store.applyActivityEvent(event)
        store.applyActivityEvent(event)
        #expect(store.refreshToken == first + 2)
    }

    // MARK: resync()

    @Test("resync increments refreshToken")
    func resyncIncrementsToken() async {
        let store = makeStore()
        let before = store.refreshToken
        await store.resync()
        #expect(store.refreshToken == before + 1)
    }

    @Test("resync called twice increments token twice")
    func resyncTwiceIncrementsTokenTwice() async {
        let store = makeStore()
        await store.resync()
        await store.resync()
        #expect(store.refreshToken == 2)
    }

    // MARK: Initial state

    @Test("refreshToken starts at zero")
    func refreshTokenInitialValue() {
        let store = makeStore()
        #expect(store.refreshToken == 0)
    }
}
