//
//  TrainedModelsStoreTests.swift
//  FicheroTests
//
//  `source.model.node-in-sidebar` and `source.model.node-inspector` (#5439): a project's
//  Training node lists the models Fichero trained, and selecting one shows its Inspector.
//  Driven through the real store and the generated client against a stub scoped to
//  /api/training/model(s), replying with the route shapes recorded from the engine's own
//  `training/model_nodes.py` (`TrainedModelPreviewFixtures`), so no other suite's requests race it.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class TrainedModelsMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?
    nonisolated(unsafe) static var paths: [String] = []
    override static func canInit(with request: URLRequest) -> Bool {
        let path = request.url?.path ?? ""
        return path == "/api/training/models" || path == "/api/training/model"
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        guard let handler = TrainedModelsMockURLProtocol.requestHandler else {
            client?.urlProtocol(self, didFailWithError: URLError(.notConnectedToInternet)); return }
        TrainedModelsMockURLProtocol.paths.append(request.url?.path ?? "")
        do { let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data); client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}

@MainActor
@Suite(.serialized)
struct TrainedModelsStoreTests {
    private let projectId = UUID(uuidString: "6F2A0A6E-2C2B-4B49-9E9B-000000000439")!

    private func makeStore(listJSON: String = TrainedModelPreviewFixtures.listJSON) -> TrainedModelsStore {
        TrainedModelsMockURLProtocol.paths = []
        TrainedModelsMockURLProtocol.requestHandler = { request in
            let path = request.url?.path ?? ""
            if path == "/api/training/models" { return Self.reply(request, 200, listJSON) }
            let model = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?
                .queryItems?.first(where: { $0.name == "model" })?.value ?? ""
            guard let json = TrainedModelPreviewFixtures.inspectorJSON(for: model) else {
                return Self.reply(request, 404, #"{"detail":"No trained model"}"#)
            }
            return Self.reply(request, 200, json)
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [TrainedModelsMockURLProtocol.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://test.fichero")!,
            libraryPath: "/tmp/test.fichero",
            session: URLSession(configuration: configuration)
        )
        return TrainedModelsStore(client: client)
    }

    private static func reply(_ request: URLRequest, _ status: Int, _ json: String) -> (HTTPURLResponse, Data) {
        let response = HTTPURLResponse(
            url: request.url!, statusCode: status, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
        return (response, Data(json.utf8))
    }

    @Test("the Training node lists every trained model, newest first, from the engine's list")
    func trainingNodeListsTrainedModels() async {
        // WHY: the node is where a person finds the models Fichero made; if the store dropped or
        // reordered the engine's list, a model would be trained and then nowhere to be found.
        let store = makeStore()
        await store.loadModels()
        #expect(TrainedModelsMockURLProtocol.paths == ["/api/training/models"])
        #expect(store.showsTrainingNode)
        #expect(store.models.map(\.name) == ["Notebook reader", "Qwen student"])
        #expect(store.models.map(\.id) == [TrainedModelPreviewFixtures.readerId, TrainedModelPreviewFixtures.studentId])
        #expect(store.errorMessage == nil)
    }

    @Test("with no trained model the Training node is hidden")
    func trainingNodeHiddenWhenEmpty() async {
        // WHY: #5413's rule, a sidebar row appears only when non-empty; an empty Training node
        // in every project would be chrome that leads nowhere.
        let store = makeStore(listJSON: #"{"models": []}"#)
        await store.loadModels()
        #expect(TrainedModelsMockURLProtocol.paths == ["/api/training/models"])
        #expect(store.models.isEmpty)
        #expect(!store.showsTrainingNode)
    }

    @Test("selecting a model row routes the Inspector to that model, and a pane pick outranks it")
    func selectingAModelRoutesTheInspector() {
        // WHY: the row's tag is a typed destination the Inspector reads back; if the id did not
        // round-trip (a model id holds "/"), the click would inspect nothing or the wrong model.
        let destination = SidebarDestination.trainedModel(TrainedModelPreviewFixtures.studentId, libraryId: projectId)
        #expect(SidebarDestination(serializedID: destination.serializedID) == destination)

        let state = SidebarSelectionState()
        state.selectedItemId = destination.serializedID
        let inspected = state.inspectedTrainedModel(browserSelection: [])
        #expect(inspected?.modelId == TrainedModelPreviewFixtures.studentId)
        #expect(inspected?.libraryId == projectId)
        #expect(state.inspectedProjectId(browserSelection: []) == nil)
        // The newer pick in the Library pane is what the Inspector follows.
        #expect(state.inspectedTrainedModel(browserSelection: ["image-1"]) == nil)
        // The Library pane lists the project, never an outline fetched for the model id.
        #expect(
            SidebarSourceOpen.libraryPaneFolderId(
                selectedItemId: destination.serializedID, viewMode: .library(nil), libraryId: projectId
            ) == SidebarDestination.library(projectId).serializedID
        )
    }

    @Test("the Inspector reads the selected model through the store, one entry in place")
    func inspectorLoadsTheSelectedModel() async {
        // WHY: the Inspector must show THIS model's card, and reading one model must not touch
        // the list (a wholesale reload resets the sidebar's selection).
        let store = makeStore()
        await store.loadModels()
        let listed = store.models.map(\.id)
        await store.loadModel(TrainedModelPreviewFixtures.studentId)
        #expect(TrainedModelsMockURLProtocol.paths == ["/api/training/models", "/api/training/model"])
        #expect(store.inspected[TrainedModelPreviewFixtures.studentId]?.name == "Qwen student")
        #expect(store.inspected[TrainedModelPreviewFixtures.readerId] == nil)
        #expect(store.models.map(\.id) == listed)
    }

    @Test("a model never evaluated says Not evaluated yet, and its unknown licence says Unknown")
    func nullScoresSayNotEvaluated() async throws {
        // WHY: a null score must not read as 0% CER (a perfect model) or vanish; the person
        // needs to know the model has not been tested on held-out pages yet.
        let store = makeStore()
        await store.loadModel(TrainedModelPreviewFixtures.readerId)
        let model = try #require(store.inspected[TrainedModelPreviewFixtures.readerId])
        let facts = ModelNodeFacts(model)
        #expect(facts.scores == nil)
        #expect(ModelNodeFacts.notEvaluated == "Not evaluated yet")
        #expect(facts.licence == "Unknown")
        #expect(facts.base == "kraken-mccatmus")
        #expect(facts.trainedWhere == "Hugging Face Jobs")
        #expect(facts.trainingSet.map(\.label).contains("Held-out pages"))
        #expect(facts.trainingSet.first(where: { $0.label == "Lines" })?.value == "210")
    }

    @Test("an evaluated model shows its newest held-out CER per policy")
    func evaluatedScoresPerPolicy() async throws {
        // WHY: the scores are how a trained model is judged against one that can be downloaded;
        // each normalisation policy is its own number and must not be merged or dropped.
        let store = makeStore()
        await store.loadModel(TrainedModelPreviewFixtures.studentId)
        let facts = ModelNodeFacts(try #require(store.inspected[TrainedModelPreviewFixtures.studentId]))
        #expect(facts.scores?.map(\.policy) == ["diplomatic", "layout-insensitive"])
        #expect(facts.scores?.map(\.cer) == [ModelNodeFacts.percent(0.051), ModelNodeFacts.percent(0.031)])
        #expect(facts.licence == "apache-2.0")
        #expect(facts.runsOn.count == 2)
    }

    @Test("may_publish false says why plainly; true says it may be published")
    func publishAvailabilitySaysWhy() async throws {
        // WHY: a model trained on material not for release must not look publishable; the
        // person reads the reason, not a bare disabled state.
        let store = makeStore()
        await store.loadModel(TrainedModelPreviewFixtures.readerId)
        await store.loadModel(TrainedModelPreviewFixtures.studentId)
        let reader = ModelNodeFacts(try #require(store.inspected[TrainedModelPreviewFixtures.readerId]))
        let student = ModelNodeFacts(try #require(store.inspected[TrainedModelPreviewFixtures.studentId]))
        #expect(!reader.mayPublish)
        #expect(reader.publish == "This model was trained on material not for release")
        #expect(student.mayPublish)
        #expect(student.publish == "May be published")
    }

    @Test("a model the engine has no card for says so in the Inspector")
    func unknownModelSaysSo() async {
        // WHY: fail loudly; a 404 must not leave the Inspector spinning forever.
        let store = makeStore()
        await store.loadModel("fichero-trained/gone")
        #expect(store.inspected["fichero-trained/gone"] == nil)
        #expect(store.inspectErrors["fichero-trained/gone"] == "Fichero has no training card for this model.")
    }
}
