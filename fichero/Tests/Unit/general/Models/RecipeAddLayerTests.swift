//
//  RecipeAddLayerTests.swift
//  FicheroTests
//
//  A layer added to a project later, from the Inspector (`source.onboard.add-layer`, #5470).
//  Written from the spec: the engine adds the layer's steps and proposes its jobs for the pages
//  already there, with the estimate and each step's topic; nothing runs until Start; Remove
//  withdraws them; and no save from setup or the Inspector may drop a layer the engine added.
//
//  Through the real `RecipeSetupStore` over the generated client. Only the transport is stubbed,
//  on this suite's own session, and it answers with responses recorded from the engine's own
//  routes (`fichero-server/tests/unit/api/test_add_a_layer_later.py`), kept in
//  `Tests/Fixtures/recipes/*.route.json` as {request, status, response}.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class AddLayerURLProtocol: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest, [String: Any]) -> (Int, Data))?
    struct Seen { let method: String; let path: String; let body: [String: Any] }
    nonisolated(unsafe) static var seen: [Seen] = []

    override static func canInit(with request: URLRequest) -> Bool {
        let path = request.url?.path ?? ""
        return path.hasPrefix("/api/recipes") || path.hasPrefix("/api/topics")
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let body = (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
        Self.seen.append(Seen(method: request.httpMethod ?? "GET", path: request.url?.path ?? "", body: body))
        let (status, data) = Self.handler?(request, body) ?? (404, Data("{}".utf8))
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor
@Suite(.serialized)
struct RecipeAddLayerTests {

    /// A route the engine answered, as recorded: its status and response body.
    private static func recorded(_ name: String) throws -> (Int, Data) {
        // Tests/Unit/general/Models/<this file> → Tests/Fixtures/recipes (a recorded response, not app source).
        let tests = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let url = tests.appendingPathComponent("Fixtures/recipes/\(name).route.json")
        let record = try #require(try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        let status = try #require(record["status"] as? Int)
        return (status, try JSONSerialization.data(withJSONObject: record["response"] ?? NSNull()))
    }

    /// The project as it stood before the layer: set up to transcribe Spanish, started.
    private static let before = Data(#"""
        {"answers":{"purpose":"transcribe","languages":["es"],"scripts":["Latn"],"material":"handwriting",
          "mac_memory_gb":16},
         "recipe":{"id":"generated/transcribe-es-Latn","title":"t","purposes":["transcribe"],
          "steps":[{"id":"read","job":"read-a-line","reasons":[]}],"gaps":[],"problems":[]}}
        """#.utf8)

    /// A store over the recorded engine: the layers route adds (or removes) entities, the
    /// project reads back as the engine left it, and Start runs the proposed jobs.
    private func makeStore() throws -> RecipeSetupStore {
        let added = try Self.recorded("add_entities_after_start")
        let removed = try Self.recorded("remove_entities_before_start")
        let afterAdd = try Self.recorded("project_after_adding_entities")
        let started = try Self.recorded("start_runs_the_proposed_jobs")
        var layerAdded = false
        AddLayerURLProtocol.seen = []
        AddLayerURLProtocol.handler = { request, body in
            switch (request.httpMethod, request.url?.path) {
            case ("POST", "/api/recipes/project/layers"):
                let remove = body["remove"] as? Bool ?? false
                layerAdded = !remove
                return remove ? removed : added
            case ("GET", "/api/recipes/project"):
                return layerAdded ? afterAdd : (200, Self.before)
            case ("POST", "/api/recipes/project/start"):
                return started
            case ("POST", "/api/recipes/assemble"):
                // The recipe the engine assembled with the layer, as the project saved it.
                let project = (try? JSONSerialization.jsonObject(with: afterAdd.1)) as? [String: Any]
                return (200, (try? JSONSerialization.data(withJSONObject: project?["recipe"] ?? [:])) ?? Data())
            case ("PUT", "/api/recipes/project"):
                return (200, Data(#"{"answers":{},"recipe":null}"#.utf8))
            default:
                return (404, Data("{}".utf8))
            }
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [AddLayerURLProtocol.self]
        let client = FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/test.fichero",
                                   session: URLSession(configuration: configuration))
        return RecipeSetupStore(client: client)
    }

    /// WHY: a historian who began with "Just transcribe" and later wants names found must see,
    /// before anything runs, which jobs the layer brings for the pages already there, what it
    /// costs and where it runs, and why each job is there (its topic). If the store dropped
    /// the engine's proposal or estimate, the person would press Start blind; if adding sent
    /// Start, a model would run over a thousand pages nobody agreed to.
    @Test("adding a layer shows its proposed jobs with the estimate and each job's topic, starting nothing")
    func addingALayerProposesItsJobs() async throws {
        let store = try makeStore()
        await store.loadSaved()

        #expect(await store.changeLayer("entities"))

        let post = try #require(AddLayerURLProtocol.seen.first { $0.path == "/api/recipes/project/layers" })
        #expect(post.body["layers"] as? [String] == ["entities"])
        #expect(post.body["remove"] as? Bool != true, "adding is not removing")
        let proposed = try #require(store.proposedJobs, "the engine's proposal is shown")
        #expect(proposed.layers == ["entities"])
        let step = try #require(proposed.steps.first)
        #expect(step.job == "find-names-tag-words" && step.layer == "entities")
        #expect(step.topic == "find-names-tag-words", "each job names the topic that explains it")
        #expect(step.title == "Find names" && !step.explanation.isEmpty, "the topic's words, not the app's")
        let plan = try #require(store.startPlan)
        #expect(plan.estimate.pages == 3, "the estimate covers the pages already there")
        #expect(plan.estimate.runs.map(\.pages) == [3])
        #expect(RecipeStartFields.cost(plan.estimate.totalCostUsd) == "free, runs on this Mac")
        #expect(store.layers == ["entities"], "the added layer is read back from the project")
        #expect(store.addableLayers == ["graph", "places", "vectors"], "the engine says what can be added now")
        #expect(!AddLayerURLProtocol.seen.contains { $0.path.hasSuffix("/start") }, "nothing starts")
    }

    /// WHY: "remove before Start withdraws its proposed jobs". If Remove left the proposal on
    /// screen, or did not send `remove`, the person would think the layer gone while its jobs
    /// still waited to run at the next Start.
    @Test("remove takes the layer out and withdraws its proposed jobs")
    func removeWithdrawsTheProposal() async throws {
        let store = try makeStore()
        await store.loadSaved()
        await store.changeLayer("entities")
        #expect(store.proposedJobs != nil)

        #expect(await store.changeLayer("entities", remove: true))

        let post = try #require(AddLayerURLProtocol.seen.last { $0.path == "/api/recipes/project/layers" })
        #expect(post.body["remove"] as? Bool == true)
        #expect(post.body["layers"] as? [String] == ["entities"])
        #expect(store.proposedJobs == nil, "no proposed jobs are left")
        #expect(store.layers.isEmpty, "the layer is gone from the project's answers")
        #expect(store.addableLayers.contains("entities"), "and can be added again")
    }

    /// WHY (the engine worker's warning): the engine keeps an added layer in `answers.layers`
    /// and its steps in the recipe. Setup and the Inspector save the whole answers and recipe;
    /// if a save carried only the fields setup asks about, the next Continue in Set Up… or a
    /// language added in the Inspector would silently drop the layer the person added, and
    /// fields the engine wrote that setup never asks (`mac_memory_gb`) with it.
    @Test("a save after adding a layer keeps the layer, its steps and the engine's other answers")
    func aSaveKeepsTheAddedLayer() async throws {
        let store = try makeStore()
        await store.loadSaved()
        await store.changeLayer("entities")

        #expect(await store.save())

        let put = try #require(AddLayerURLProtocol.seen.last { $0.method == "PUT" })
        let answers = try #require(put.body["answers"] as? [String: Any])
        #expect(answers["layers"] as? [String] == ["entities"], "the added layer survives a save")
        #expect(answers["mac_memory_gb"] as? Int == 16, "a field setup never asks survives a save")
        #expect(answers["languages"] as? [String] == ["es"])
        let recipe = try #require(put.body["recipe"] as? [String: Any])
        let jobs = (recipe["steps"] as? [[String: Any]] ?? []).compactMap { $0["job"] as? String }
        #expect(jobs.contains("find-names-tag-words"), "the layer's step stays in the saved recipe")
    }

    /// WHY: a language added in the Inspector re-proposes the recipe from the answers. If the
    /// re-proposal left out the added layers, the new recipe (then saved) would lose the
    /// layer's steps even though its answers kept it.
    @Test("a recipe proposed again after adding a layer asks for the layer too")
    func reassemblingCarriesTheLayer() async throws {
        let store = try makeStore()
        await store.loadSaved()
        await store.changeLayer("entities")
        AddLayerURLProtocol.seen = []

        await store.updateLanguages(["es", "la"])

        let assemble = try #require(AddLayerURLProtocol.seen.first { $0.path == "/api/recipes/assemble" })
        #expect(assemble.body["layers"] as? [String] == ["entities"])
        let put = try #require(AddLayerURLProtocol.seen.last { $0.method == "PUT" })
        let answers = try #require(put.body["answers"] as? [String: Any])
        #expect(answers["layers"] as? [String] == ["entities"])
    }

    /// WHY: the proposed jobs run only on the person's yes, through the same Start as setup
    /// (`POST /api/recipes/project/start`, audited). If Start did not post, nothing would run;
    /// once it has, the proposal is done with and must leave the Inspector.
    @Test("Start sends the start action and the proposal is done with")
    func startSendsTheStartAction() async throws {
        let store = try makeStore()
        await store.loadSaved()
        await store.changeLayer("entities")
        #expect(store.canStart, "the engine refused nothing")

        #expect(await store.start())

        #expect(AddLayerURLProtocol.seen.contains { $0.method == "POST" && $0.path == "/api/recipes/project/start" })
        #expect(store.proposedJobs == nil)
        #expect(store.startPlan?.workflows.flatMap(\.steps).contains("find-names-tag-words") == true)
    }

    /// WHY: the engine refuses what cannot be added in words. Its sentence is a string
    /// `detail`, which the generated validation shape cannot decode; if the store showed the
    /// decoding error, the person would read nonsense instead of the reason.
    @Test("a refusal shows the engine's own sentence")
    func refusalInWords() async throws {
        let refused = try Self.recorded("add_unknown_layer_refused")
        let store = try makeStore()
        AddLayerURLProtocol.handler = { _, _ in refused }

        #expect(await store.changeLayer("entities") == false)

        #expect(store.errorMessage == "this project has not been set up yet: run setup first")
    }
}
