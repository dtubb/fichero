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
}
