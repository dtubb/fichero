@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The model node's Inspector (#5439, #5539; `training.model.make-global`, `training.model.error-beside-base`): Make
/// Available in Every Project is the engine's audited `training.make_model_global` through its route, and the
/// Inspector shows the models its newest evaluation compared it with, on the same pages, as their own cards wrote
/// them. Through the real `TrainedModelsStore` over the generated client; only the transport is stubbed.
private final class ModelNodeEngine: URLProtocol {
    nonisolated(unsafe) static var lives = "project"
    struct Seen { let path: String; let query: String; let body: [String: Any] }
    nonisolated(unsafe) static var seen: [Seen] = []

    override static func canInit(with request: URLRequest) -> Bool { request.url?.host == "model-node.test" }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let path = request.url?.path ?? ""
        let body = (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
        Self.seen.append(Seen(path: path, query: request.url?.query ?? "", body: body))
        var json = "{}"
        switch path {
        case "/api/training/models":
            json = #"{"models":[{"id":"kraken-trained-0f4e","name":"Notebook reader","kind":"kraken-reader","#
                + #""may_publish":false,"lives":"\#(Self.lives)"}]}"#
        case "/api/training/model":
            json = #"{"id":"kraken-trained-0f4e","name":"Notebook reader","kind":"kraken-reader","may_publish":false,"#
                + #""lives":"\#(Self.lives)","card":{},"scores":{"pages":2,"job_id":"eval-2","#
                + #""cer":{"diplomatic":0.051}},"evaluation_history":[{"job_id":"eval-1","compared_with":["old"]},"#
                + #"{"job_id":"eval-2","compared_with":["kraken-mccatmus"]}]}"#
        case "/api/training/models/make-global":
            Self.lives = "both"
            json = #"{"model_id":"kraken-trained-0f4e","global_path":"/models/kraken-trained-0f4e","may_publish":false}"#
        case "/api/evaluation/scores":
            json = #"{"model":"kraken-mccatmus","reader":"kraken","evaluations":["#
                + #"{"job_id":"eval-1","scores":{"diplomatic":{"cer":0.31}}},"#
                + #"{"job_id":"eval-2","scores":{"diplomatic":{"cer":0.074}}}]}"#
        default:
            break
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor
@Suite(.serialized)
struct TrainedModelNodeActionsTests {
    private let modelId = "kraken-trained-0f4e"

    private func store() -> TrainedModelsStore {
        ModelNodeEngine.lives = "project"
        ModelNodeEngine.seen = []
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ModelNodeEngine.self]
        return TrainedModelsStore(client: FicheroClient(
            baseURL: URL(string: "https://model-node.test")!, libraryPath: "/tmp/model-node.fichero",
            session: URLSession(configuration: configuration)
        ))
    }

    /// WHY: a model trained in one project was usable only there; the engine's action makes it every project's, and
    /// the Inspector must say where it lives before and after, never offer it twice.
    @Test("Make Available in Every Project sends the model to the engine's action and says where it lives now")
    func makeGlobal() async throws {
        let store = store()
        await store.loadModel(modelId)
        let before = ModelNodeFacts(try #require(store.inspected[modelId]))
        #expect(before.livesOnlyHere && before.lives == "This project only")

        #expect(await store.makeGlobal(modelId) == nil)

        let sent = try #require(ModelNodeEngine.seen.first { $0.path == "/api/training/models/make-global" })
        #expect(sent.body["model"] as? String == modelId)
        let after = ModelNodeFacts(try #require(store.inspected[modelId]))
        #expect(!after.livesOnlyHere, "patched in place: not offered again")
        #expect(after.lives == "This project and every other project")
    }

    /// WHY: Project › Train, the Models node's row menu and the Inspector act through one target (#5652 slice 1):
    /// one press makes it global once, and every one of them then says it is already everywhere.
    @Test("the shared Make Available target makes the listed model global once, then says it already is")
    func makeAvailableThroughTheSharedTarget() async throws {
        let store = store()
        await store.loadModels()
        let target = try #require(TrainedModelMenuTarget.make(modelId: modelId, store: store))
        #expect(target.livesOnlyHere)
        #expect(FocusedTrainButtons.makeGlobalDisabledReason(target) == nil)

        await store.makeAvailableEverywhere(modelId)

        #expect(store.makeGlobalNotes[modelId] == nil)
        #expect(!store.makingGlobal.contains(modelId))
        #expect(!store.livesOnlyHere(modelId), "the list's entry is patched in place")
        let after = try #require(TrainedModelMenuTarget.make(modelId: modelId, store: store))
        #expect(FocusedTrainButtons.makeGlobalDisabledReason(after) == "It is already available in every project")
        #expect(ModelNodeEngine.seen.filter { $0.path == "/api/training/models/make-global" }.count == 1)
    }

    /// WHY: a model's error alone says nothing; beside its base on the same pages it says whether training helped.
    @Test("beside its base on the same pages: the compared model's score from the same evaluation job")
    func comparedOnTheSamePages() async throws {
        let store = store()
        await store.loadModel(modelId)
        await store.loadCompared(modelId)

        let compared = try #require(store.compared[modelId])
        #expect(compared == [ModelNodeFacts.Compared(model: "kraken-mccatmus", cer: ["diplomatic": 0.074])],
                "the newest evaluation's entry, not an older one")
        #expect(compared.first?.says(policy: "diplomatic") == "kraken-mccatmus: " + ModelNodeFacts.percent(0.074))
        let asked = try #require(ModelNodeEngine.seen.first { $0.path == "/api/evaluation/scores" })
        #expect(asked.query.contains("model=kraken-mccatmus") && asked.query.contains("reader=kraken"))
    }
}
