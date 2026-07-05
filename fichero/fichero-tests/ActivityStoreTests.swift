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

/// Reference box so a stored `changeRouter` closure can record what it received
/// without capturing a mutable local (avoids the escaping-capture warning).
@MainActor
private final class RoutedEvents {
    var events: [ChangeEvent] = []
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

    // MARK: Folded change frames (#3159 / #2479)

    /// Build the activity frame the backend emits for a folded change event
    /// (#3159): `system_info`, id prefixed `change-`, change payload in metadata.
    private func makeFoldedChangeFrame(
        changeType: String = "document.updated",
        documentIds: String = "[\"doc-1\",\"doc-2\"]"
    ) -> ActivityItem {
        ActivityItem(
            id: "change-abc",
            type: "system_info",
            level: "info",
            timestamp: "2026-07-05T12:00:00Z",
            message: "\(changeType) changed",
            metadataRaw: [
                "change_type": AnyValueAsString(changeType),
                "actor": AnyValueAsString("mac"),
                "document_ids": AnyValueAsString(documentIds),
                "entity_ids": AnyValueAsString("[]")
            ]
        )
    }

    @Test("ChangeEvent reconstructs from a folded activity frame's metadata")
    func changeEventFromActivityMetadata() {
        let metadata = [
            "change_type": "entity.merged",
            "actor": "ipad",
            "entity_ids": "[\"e1\",\"e2\"]",
            "document_ids": "[]"
        ]
        let change = ChangeEvent(activityMetadata: metadata)
        #expect(change?.type == "entity.merged")
        #expect(change?.domain == "entity")
        #expect(change?.entityIds == ["e1", "e2"])
        #expect(change?.actor == "ipad")
    }

    @Test("ChangeEvent(activityMetadata:) is nil for an ordinary activity frame")
    func changeEventNilWithoutChangeType() {
        #expect(ChangeEvent(activityMetadata: ["message": "hi"]) == nil)
        #expect(ChangeEvent(activityMetadata: ["change_type": ""]) == nil)
    }

    @Test("folded change frame does NOT bump refreshToken (no wholesale run reload)")
    func foldedChangeFrameDoesNotBumpToken() {
        let store = makeStore()
        let before = store.refreshToken
        store.applyActivityEvent(makeFoldedChangeFrame())
        #expect(store.refreshToken == before)
    }

    @Test("folded change frame is routed to changeRouter (remote hosts)")
    func foldedChangeFrameRoutedToRouter() {
        let store = makeStore()
        let box = RoutedEvents()
        store.changeRouter = { box.events.append($0) }
        store.applyActivityEvent(makeFoldedChangeFrame())
        #expect(box.events.count == 1)
        #expect(box.events.first?.documentIds == ["doc-1", "doc-2"])
        #expect(box.events.first?.type == "document.updated")
    }

    @Test("folded change frame with nil changeRouter is dropped (local hosts)")
    func foldedChangeFrameDroppedWhenLocal() {
        let store = makeStore()
        let before = store.refreshToken
        store.changeRouter = nil
        store.applyActivityEvent(makeFoldedChangeFrame())
        #expect(store.refreshToken == before)  // neither routed nor a run reload
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
