//
//  CloudCapStoreTests.swift
//  FicheroTests
//
//  #6295, `ai.where.cloud-spend-cap`: the store's side of changing the caps in place, through the real `RecipeSetupStore` over the
//  generated client with only the transport stubbed (on this suite's own session): what a refused change says, what a kept change
//  reads back, and that one edit is one change. The pure view logic is in `CloudCapFixTests`; the engine's amounts and refusals
//  are in fichero-server/tests/unit/recipes/test_raise_the_cap_in_place_6295.py.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class CloudCapURLProtocol: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) -> (Int, String))?
    /// The method and path of every request that reached the stub, in order.
    nonisolated(unsafe) static var seen: [String] = []

    override static func canInit(with request: URLRequest) -> Bool { request.url?.path.hasPrefix("/api/recipes") ?? false }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.seen.append("\(request.httpMethod ?? "GET") \(request.url?.path ?? "")")
        let (status, json) = Self.handler?(request) ?? (404, "{}")
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor
@Suite(.serialized)
struct CloudCapStoreTests {
    private static let plan = """
        {"runs":[],"skipped":[],"workflows":[],"offered":[],"refusals":[],
         "estimate":{"pages":49,"runs":[],"total_cost_usd":null}}
        """
    private static let saved = #"{"answers":{"cloud_spend_cap_usd":25,"cloud_project_cap_usd":60},"recipe":null}"#
    private static let changed = #"{"cap_usd":25,"project_cap_usd":60,"audit_id":"audit-1"}"#

    private func makeStore(_ handler: @escaping (URLRequest) -> (Int, String)) -> RecipeSetupStore {
        CloudCapURLProtocol.handler = handler
        CloudCapURLProtocol.seen = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CloudCapURLProtocol.self]
        let client = FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/test.fichero",
                                   session: URLSession(configuration: configuration))
        return RecipeSetupStore(client: client)
    }

    /// An engine that keeps the change: the PUT, the answers read back, the plan read again.
    private static func keeping(_ request: URLRequest) -> (Int, String) {
        switch (request.httpMethod, request.url?.path) {
        case ("PUT", "/api/recipes/project/cloud-cap"): return (200, changed)
        case ("GET", "/api/recipes/project"): return (200, saved)
        case ("GET", "/api/recipes/project/start"): return (200, plan)
        default: return (404, "{}")
        }
    }

    /// WHY: the Raise buttons cleared the error, but a field edit did not, so a "Start is refused…" label stayed beside the cap
    /// that had just been fixed until the next Start.
    @Test("a kept cap change clears the error of the refused Start, from a field edit too")
    func aFieldEditClearsTheStaleError() async {
        defer { CloudCapURLProtocol.handler = nil }
        let store = makeStore(Self.keeping)
        store.errorMessage = "Start is refused: This run is estimated at US$14.00 of cloud spending."
        #expect(await store.changeCloudCaps(monthlyUsd: 25))
        #expect(store.errorMessage == nil)
    }

    /// WHY: a cap the engine refuses must say so in its words and change nothing on screen: the store held the old caps, the plan was
    /// not read again, and no undo step was made for a change that did not happen.
    @Test("a cap the engine refuses in a sentence says it, and the plan is not read again")
    func aRefusedCapSaysItsSentence() async {
        defer { CloudCapURLProtocol.handler = nil }
        let store = makeStore { request in
            request.httpMethod == "PUT" ? (422, #"{"detail":"The cloud spending cap is a number of dollars, 0 or more."}"#) : (404, "{}")
        }
        store.cloudSpendCapUsd = 10
        #expect(await store.changeCloudCaps(monthlyUsd: 25) == false)
        #expect(store.errorMessage == "The cloud spending cap is a number of dollars, 0 or more.")
        #expect(store.cloudSpendCapUsd == 10, "the held cap is the engine's, not the one asked for")
        #expect(CloudCapURLProtocol.seen == ["PUT /api/recipes/project/cloud-cap"], "no answers read back, no plan read again")
    }

    /// WHY: the route's own field checks (a cap below 0, a project cap set and cleared together) answer in FastAPI's field-error
    /// array, which the declared sentence shape cannot decode: the client threw, and the screen showed the decoder's words.
    @Test("a refusal in FastAPI's field-error shape says the engine's words, not the decoder's")
    func aFieldErrorShapedRefusalSaysItsWords() async {
        defer { CloudCapURLProtocol.handler = nil }
        let store = makeStore { _ in
            (422, #"{"detail":[{"type":"value_error","loc":["body"],"msg":"Value error, a project cap is set or cleared, not both"}]}"#)
        }
        #expect(await store.changeCloudCaps(monthlyUsd: 25) == false)
        let words = store.errorMessage ?? ""
        #expect(words.contains("a project cap is set or cleared, not both"), "got: \(words)")
    }

    /// WHY: after a kept change the store holds the caps as the engine now has them, and the saved answers a later save starts from, so
    /// a cap cleared (or put back by an undo) is never written back by the next save; the plan is read again, so it says whether
    /// Start still asks.
    @Test("a kept change adopts the caps the engine now holds and reads the plan again")
    func aKeptChangeAdoptsTheSavedCaps() async throws {
        defer { CloudCapURLProtocol.handler = nil }
        let store = makeStore(Self.keeping)
        #expect(await store.changeCloudCaps(monthlyUsd: 25, projectUsd: 60))
        #expect(store.cloudSpendCapUsd == 25 && store.cloudProjectCapUsd == 60)
        let kept = try #require(store.savedAnswers.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any])
        #expect(kept["cloud_spend_cap_usd"] as? Double == 25 && kept["cloud_project_cap_usd"] as? Double == 60)
        #expect(CloudCapURLProtocol.seen == [
            "PUT /api/recipes/project/cloud-cap", "GET /api/recipes/project", "GET /api/recipes/project/start"
        ])
        #expect(store.startPlan != nil)
    }

    /// WHY: clearing the project cap must read back as no limit, or the next save would put the old one back.
    @Test("a cleared project cap reads back as no limit")
    func aClearedProjectCapReadsBackAsNoLimit() async {
        defer { CloudCapURLProtocol.handler = nil }
        let store = makeStore { request in
            switch (request.httpMethod, request.url?.path) {
            case ("PUT", "/api/recipes/project/cloud-cap"): return (200, #"{"cap_usd":25,"audit_id":"audit-2"}"#)
            case ("GET", "/api/recipes/project"): return (200, #"{"answers":{"cloud_spend_cap_usd":25},"recipe":null}"#)
            default: return (200, Self.plan)
            }
        }
        store.cloudProjectCapUsd = 60
        #expect(await store.changeCloudCaps(clearProjectCap: true))
        #expect(store.cloudProjectCapUsd == nil && store.cloudSpendCapUsd == 25)
    }
}
