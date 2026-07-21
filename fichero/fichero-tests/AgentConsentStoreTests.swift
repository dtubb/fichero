import Foundation
import XCTest

@testable import Fichero

// #1847 (UI prototype): the consent store's session-memory and single-prompt
// gating are the logic worth pinning. The "for the session" rule is that a
// remembered decision short-circuits the prompt; nothing here persists, so a
// fresh store (a relaunch stand-in) has no memory.
@MainActor
final class AgentConsentStoreTests: XCTestCase {
    /// Yield until the store registers a pending request (the awaiting task has
    /// suspended on its continuation), or fail after a bounded number of hops.
    private func waitForPending(_ store: AgentConsentStore) async {
        for _ in 0..<100 where store.pending == nil {
            await Task.yield()
        }
        XCTAssertNotNil(store.pending, "requestConsent should have raised a pending request")
    }

    func testApproveResolvesAndClearsPending() async {
        let store = AgentConsentStore()
        let task = Task { await store.requestConsent(AgentConsentRequest(clientName: "Agent A")) }
        await waitForPending(store)

        store.resolve(approved: true, remember: false)
        let approved = await task.value

        XCTAssertTrue(approved)
        XCTAssertNil(store.pending)
        // Not remembered → no session decision recorded.
        XCTAssertNil(store.rememberedDecision(for: "Agent A"))
    }

    func testRememberedApprovalSkipsSecondPrompt() async {
        let store = AgentConsentStore()
        let first = Task { await store.requestConsent(AgentConsentRequest(clientName: "Agent A")) }
        await waitForPending(store)
        store.resolve(approved: true, remember: true)
        _ = await first.value

        // Second connect from the same client returns immediately, no prompt.
        let second = await store.requestConsent(AgentConsentRequest(clientName: "Agent A"))
        XCTAssertTrue(second)
        XCTAssertNil(store.pending)
        XCTAssertEqual(store.rememberedDecision(for: "Agent A"), true)
    }

    func testRememberedDenialSkipsSecondPrompt() async {
        let store = AgentConsentStore()
        let first = Task { await store.requestConsent(AgentConsentRequest(clientName: "Agent B")) }
        await waitForPending(store)
        store.resolve(approved: false, remember: true)
        _ = await first.value

        let second = await store.requestConsent(AgentConsentRequest(clientName: "Agent B"))
        XCTAssertFalse(second)
        XCTAssertNil(store.pending)
        XCTAssertEqual(store.rememberedDecision(for: "Agent B"), false)
    }

    func testConcurrentSecondRequestIsDeniedWithoutStacking() async {
        let store = AgentConsentStore()
        let first = Task { await store.requestConsent(AgentConsentRequest(clientName: "Agent A")) }
        await waitForPending(store)

        // A different client connects while the first prompt is still open.
        let second = await store.requestConsent(AgentConsentRequest(clientName: "Agent C"))
        XCTAssertFalse(second, "a second concurrent request is denied rather than stacking sheets")
        // The first prompt is untouched.
        XCTAssertEqual(store.pending?.clientName, "Agent A")

        store.resolve(approved: true, remember: false)
        XCTAssertTrue(await first.value)
    }
}
