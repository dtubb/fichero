//
//  ActivityStoreTests.swift
//  FicheroTests
//
//  Unit tests for ActivityStore (#2448).  Verifies that the change-stream
//  consumer plumbing — `changeDomains`, `apply(_:)`, `resync()` — produces
//  the expected `refreshToken` increments so `ActivityBrowserView` reloads.
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

    @Test("changeDomains contains \"workflow\" so store reacts to workflow SSE events")
    func changeDomainIsWorkflow() {
        let store = makeStore()
        #expect(store.changeDomains.contains("workflow"))
    }

    @Test("changeDomains does not contain unrelated domains")
    func changeDomainExcludesOthers() {
        let store = makeStore()
        #expect(!store.changeDomains.contains("document"))
        #expect(!store.changeDomains.contains("entity"))
        #expect(!store.changeDomains.contains("activity"))
    }

    // MARK: apply(_:)

    @Test("apply increments refreshToken once per event")
    func applySingleEventIncrementsToken() throws {
        let store = makeStore()
        let before = store.refreshToken
        let event = try makeEvent(domain: "workflow", verb: "created")
        store.apply(event)
        #expect(store.refreshToken == before + 1)
    }

    @Test("apply increments refreshToken independently for each event")
    func applyMultipleEventsIncrementToken() throws {
        let store = makeStore()
        let event = try makeEvent(domain: "workflow", verb: "updated")
        store.apply(event)
        store.apply(event)
        store.apply(event)
        #expect(store.refreshToken == 3)
    }

    @Test("duplicate events each bump refreshToken (no dedup — caller controls)")
    func applyDuplicateEventBumpsEveryTime() throws {
        let store = makeStore()
        let event = try makeEvent(domain: "workflow")
        let first = store.refreshToken
        store.apply(event)
        store.apply(event)
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
