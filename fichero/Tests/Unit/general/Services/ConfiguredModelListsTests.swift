@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// spec: ai-settings `settings.models.pickers-share-one-fetch` (#6376): the pickers opened together
/// share one configured-models fetch per provider, and a provider with no model list (404) is an
/// empty list, not an error.
@MainActor
struct ConfiguredModelListsTests {
    private func model() throws -> Components.Schemas.UserModelResponse {
        let json = Data("""
        {"id":"m1","provider_id":"p1","name":"M","model_id":"m","capabilities":[],
         "is_default":false,"enabled":true,"input_cost":0,"output_cost":0}
        """.utf8)
        return try JSONDecoder().decode(Components.Schemas.UserModelResponse.self, from: json)
    }

    private final class Counter { var calls = 0 }

    @Test("ten pickers asking at once make one request")
    func concurrentCallersShareOneFetch() async throws {
        let lists = ConfiguredModelLists()
        let counter = Counter()
        let row = try model()
        let fetch: @MainActor () async throws -> ConfiguredModelLists.Models = {
            counter.calls += 1
            try await Task.sleep(for: .milliseconds(50))
            return [row]
        }
        await withThrowingTaskGroup(of: Int.self) { group in
            for _ in 0..<10 {
                group.addTask { try await lists.models(providerId: "p1", fetch: fetch).count }
            }
        }
        #expect(counter.calls == 1)
    }

    @Test("a provider with no model list (HTTP 404) has an empty list, not an error")
    func notFoundIsEmpty() async throws {
        let lists = ConfiguredModelLists()
        let result = try await lists.models(providerId: "omlx") { throw ProviderAPIServiceError.unexpectedResponse(404) }
        #expect(result.isEmpty)
    }

    @Test("any other failure is still an error")
    func otherErrorsPropagate() async {
        let lists = ConfiguredModelLists()
        await #expect(throws: ProviderAPIServiceError.self) {
            try await lists.models(providerId: "p1") { throw ProviderAPIServiceError.unexpectedResponse(500) }
        }
    }

    @Test("a later open fetches again once the reuse window has passed")
    func fetchesAgainAfterTheWindow() async throws {
        var clock = Date(timeIntervalSince1970: 1_000)
        let lists = ConfiguredModelLists(now: { clock })
        let counter = Counter()
        let fetch: @MainActor () async throws -> ConfiguredModelLists.Models = { counter.calls += 1; return [] }
        _ = try await lists.models(providerId: "p1", fetch: fetch)
        _ = try await lists.models(providerId: "p1", fetch: fetch)
        #expect(counter.calls == 1)
        clock = clock.addingTimeInterval(ConfiguredModelLists.reuseSeconds + 1)
        _ = try await lists.models(providerId: "p1", fetch: fetch)
        #expect(counter.calls == 2)
    }

    @Test("each provider has its own fetch")
    func providersAreIndependent() async throws {
        let lists = ConfiguredModelLists()
        let counter = Counter()
        let fetch: @MainActor () async throws -> ConfiguredModelLists.Models = { counter.calls += 1; return [] }
        _ = try await lists.models(providerId: "a", fetch: fetch)
        _ = try await lists.models(providerId: "b", fetch: fetch)
        #expect(counter.calls == 2)
    }
}
