@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Pure change-stream contract tests for the action-domain store. Network-backed
/// reload behavior belongs to the service integration tests.
@MainActor
@Suite("ActionStore")
struct ActionStoreTests {

    private static func client() -> FicheroClient {
        FicheroClient(baseURL: EngineConfig.host, transportMode: EngineConfig.transportMode)
    }

    @Test("registers only the action change domain")
    func changeDomain() {
        let store = ActionStore(service: ActionsService(client: Self.client()))

        #expect(store.changeDomain == "action")
        #expect(store.changeDomains == ["action"])
    }

    @Test("every action event advances the change token")
    func actionEventsAdvanceChangeToken() throws {
        let store = ActionStore(service: ActionsService(client: Self.client()))

        for verb in ["created", "updated", "deleted", "used"] {
            store.apply(try event(verb))
            // Prevent the mutation verbs' deferred reload from reaching localhost.
            store.reloadDebouncer.cancel()
        }

        #expect(store.changeToken == 4)
    }

    @Test("change events do not synchronously replace cached actions")
    func changeEventsLeaveCachedActionsUntilReload() throws {
        let store = ActionStore(service: ActionsService(client: Self.client()))

        store.apply(try event("created"))
        store.reloadDebouncer.cancel()

        #expect(store.actions.isEmpty)
        #expect(store.loadError == nil)
    }

    private func event(_ verb: String) throws -> ChangeEvent {
        let data = try JSONSerialization.data(withJSONObject: ["type": "action.\(verb)"])
        return try JSONDecoder().decode(ChangeEvent.self, from: data)
    }
}
