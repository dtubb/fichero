@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private struct SeenRequest {
    let method: String
    let url: URL
    let body: Data
}

private final class EmbeddingRoutesURLProtocol: URLProtocol {
    nonisolated(unsafe) static var seen: [SeenRequest] = []
    nonisolated(unsafe) static var startStatus = 200

    override static func canInit(with request: URLRequest) -> Bool {
        let path = request.url?.path ?? ""
        return path.hasPrefix("/api/search/embedding") || path == "/api/library"
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let url = request.url!
        Self.seen.append(SeenRequest(method: request.httpMethod ?? "GET", url: url, body: request.bodyOrStream()))
        var status = 200
        var json = "{}"
        switch (request.httpMethod ?? "GET", url.path) {
        case ("GET", "/api/search/embedding"):
            json = #"{"model":"BAAI/bge-m3","models":["BAAI/bge-m3","intfloat/multilingual-e5-large"],"vectors":12,"changeable":false}"#
        case ("GET", "/api/search/embedding/change-plan"):
            json = #"""
                {"from_model":"BAAI/bge-m3","to_model":"intfloat/multilingual-e5-large","same":false,"pages":3,"passages":40,
                 "entities":2,"claims":1,"seconds_estimate":130,"cost_usd":0.0,"runs_on":"this-mac",
                 "keeps_old_vectors_until_done":true}
                """#
        case ("POST", "/api/search/embedding/change"):
            status = Self.startStatus
            json = status == 200
                ? #"{"status":"started","job_id":"j1","message":"Embedding 3 pages. Search keeps the old vectors until it finishes."}"#
                : #"{"detail":"This project already searches with intfloat/multilingual-e5-large."}"#
        case ("POST", "/api/library"):
            json = #"{"path":"/tmp/P.fichero","created":true,"tables_initialized":true}"#
        default:
            status = 404
        }
        let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

/// #6122 (`search.embedding.change-is-a-re-embed-run`, `search.embedding.chosen-at-project-creation`): the app shows which
/// search model the project uses, says what changing it would cost before anything runs, and starts the run only for the
/// plan the person has seen. The engine is a stubbed transport.
@MainActor
@Suite(.serialized)
struct EmbeddingChangeStoreTests {
    private func makeClient() -> FicheroClient {
        EmbeddingRoutesURLProtocol.seen = []
        EmbeddingRoutesURLProtocol.startStatus = 200
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [EmbeddingRoutesURLProtocol.self]
        return FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/test.fichero",
                             session: URLSession(configuration: configuration))
    }

    @Test("it reads which model the project uses and how many vectors it holds")
    func loadsTheCurrentChoice() async {
        let store = EmbeddingChangeStore(client: makeClient())
        await store.load()
        #expect(store.current?.model == "BAAI/bge-m3" && store.current?.vectors == 12)
    }

    @Test("the plan is asked for the chosen model and said in words before anything runs")
    func planFirst() async throws {
        let store = EmbeddingChangeStore(client: makeClient())
        await store.loadPlan(for: "intfloat/multilingual-e5-large")
        let asked = try #require(EmbeddingRoutesURLProtocol.seen.last)
        #expect(URLComponents(url: asked.url, resolvingAgainstBaseURL: false)?.queryItems?
            .first { $0.name == "model" }?.value == "intfloat/multilingual-e5-large")
        let plan = try #require(store.plan)
        #expect(EmbeddingChangeStore.sentence(for: plan)
                == "Embeds 3 pages, 2 names, 1 statement again with multilingual-e5-large: about 2 minutes, free, it runs on this Mac.")
        #expect(!EmbeddingRoutesURLProtocol.seen.contains { $0.method == "POST" }, "nothing runs while the plan is read")
    }

    @Test("start sends the plan's model with confirm, only after a plan, and says where it shows")
    func startsTheSeenPlan() async throws {
        let store = EmbeddingChangeStore(client: makeClient())
        await store.start()
        #expect(EmbeddingRoutesURLProtocol.seen.isEmpty, "no plan, no run")
        await store.loadPlan(for: "intfloat/multilingual-e5-large")
        await store.start()
        let post = try #require(EmbeddingRoutesURLProtocol.seen.last { $0.method == "POST" })
        let body = try #require(try JSONSerialization.jsonObject(with: post.body) as? [String: Any])
        #expect(body["model"] as? String == "intfloat/multilingual-e5-large" && body["confirm"] as? Bool == true)
        #expect(store.started?.jobId == "j1")
        #expect(store.started?.message.contains("Search keeps the old vectors") == true)
    }

    @Test("a refusal from the engine is shown in its own words and nothing is started")
    func refusal() async {
        let store = EmbeddingChangeStore(client: makeClient())
        await store.loadPlan(for: "intfloat/multilingual-e5-large")
        EmbeddingRoutesURLProtocol.startStatus = 409
        await store.start()
        #expect(store.started == nil)
        #expect(store.errorMessage == "This project already searches with intfloat/multilingual-e5-large.")
    }

    @Test("times read as an estimate")
    func timeWords() {
        #expect(EmbeddingChangeStore.time(seconds: 20) == "under a minute")
        #expect(EmbeddingChangeStore.time(seconds: 60) == "about 1 minute")
        #expect(EmbeddingChangeStore.time(seconds: 130) == "about 2 minutes")
        #expect(EmbeddingChangeStore.time(seconds: 7200) == "about 2.0 hours")
    }

    @Test("a new project is made with the chosen search model; bge-m3 is preselected")
    func chosenAtCreation() async throws {
        #expect(EmbeddingModelChoice.defaultModel == "BAAI/bge-m3")
        #expect(EmbeddingModelChoice.all.first?.model == EmbeddingModelChoice.defaultModel)
        let api = APIClient(client: makeClient())
        try await api.initializeLibrary(path: "/tmp/P.fichero", embeddingModel: "intfloat/multilingual-e5-large")
        let post = try #require(EmbeddingRoutesURLProtocol.seen.last { $0.url.path == "/api/library" })
        let body = try #require(try JSONSerialization.jsonObject(with: post.body) as? [String: Any])
        #expect(body["embedding_model"] as? String == "intfloat/multilingual-e5-large" && body["path"] as? String == "/tmp/P.fichero")
        try await api.initializeLibrary(path: "/tmp/Q.fichero")
        let plain = try #require(EmbeddingRoutesURLProtocol.seen.last { $0.url.path == "/api/library" })
        let plainBody = try #require(try JSONSerialization.jsonObject(with: plain.body) as? [String: Any])
        #expect(plainBody["embedding_model"] == nil, "no choice: the engine's default stands")
    }
}
