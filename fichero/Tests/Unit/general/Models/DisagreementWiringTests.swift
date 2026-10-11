@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The lens wired to the engine (#5665, `source.disagree.route`, `.recipe-step`, `.fewer-than-two`): the store reads
/// `GET /api/documents/{page_id}/disagreement` through the generated client, a refusal in the engine's words; and
/// Find Where the Readers Disagree adds the step to the project's plan, saving only once the engine's plan holds it.
private final class DisagreementEngine: URLProtocol {
    nonisolated(unsafe) static var assembleHasStep = true
    nonisolated(unsafe) static var saved: [String: Any]?
    nonisolated(unsafe) static var assembled: [String: Any]?

    override static func canInit(with request: URLRequest) -> Bool { true }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let path = request.url?.path ?? ""
        let body = (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any]
        var status = 200, json = "{}"
        switch (request.httpMethod ?? "GET", path) {
        case ("GET", "/api/documents/p1/disagreement"):
            json = ReadingDisagreementTests.json
        case ("GET", "/api/documents/missing/disagreement"):
            status = 404
            json = #"{"detail":"No page missing in this project"}"#
        case ("GET", "/api/recipes/project"):
            json = #"{"answers":{"purpose":"transcribe","languages":["la"],"scripts":["Latn"]},"recipe":null}"#
        case ("POST", "/api/recipes/assemble"):
            Self.assembled = body
            let step = Self.assembleHasStep
                ? #"{"id":"disagree","job":"find-where-readers-disagree","reasons":[]}"#
                : #"{"id":"read","job":"read-a-line","reasons":[]}"#
            json = #"{"id":"generated","title":"Latin","purposes":["transcribe"],"steps":[\#(step)],"#
                + #""gaps":[],"problems":[]}"#
        case ("PUT", "/api/recipes/project"):
            Self.saved = body
            json = #"{"answers":{},"recipe":null}"#
        default:
            status = 404
        }
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
struct DisagreementWiringTests {
    private func client() -> FicheroClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [DisagreementEngine.self]
        return FicheroClient(baseURL: URL(string: "https://127.0.0.1:8765")!, libraryPath: "/tmp/Disagree.fichero",
                             session: URLSession(configuration: configuration))
    }

    @Test("the store reads the page through the engine's route, as the app's shape")
    func readsTheRoute() async throws {
        let store = ReadingDisagreementStore(source: ReadingDisagreementStore.engine(client()))
        await store.load(pageId: "p1")
        let page = try #require(store.disagreement(of: "p1"))
        #expect(page.readers.count == 4)
        #expect(page.lines.map(\.segmentId) == ["l1", "l2"])
        #expect(page.lines[0].words[0].bbox == [10, 20, 60, 18])
        #expect(page.doubtfulRefs.count == 3, "the same walk as a decoded page")
    }

    @Test("a refusal is said in the engine's words")
    func refusalInTheEnginesWords() async {
        let store = ReadingDisagreementStore(source: ReadingDisagreementStore.engine(client()))
        await store.load(pageId: "missing")
        #expect(store.pages["missing"] == .unavailable("No page missing in this project"))
    }

    /// WHY: with fewer than two readings the lens offers the step that makes them; it must land in the project's
    /// plan, and the plan it saves must be the engine's, never the store's defaults over the project's own setup.
    @Test("Find Where the Readers Disagree adds the step to the plan the engine proposes, then saves it")
    func addsTheStep() async throws {
        DisagreementEngine.assembleHasStep = true
        DisagreementEngine.saved = nil
        let store = RecipeSetupStore(client: client())

        #expect(await store.addStep(job: DisagreementPageView.findJob))

        #expect(store.languages == ["la"], "the project's own answers were read first")
        let saved = try #require(DisagreementEngine.saved?["answers"] as? [String: Any])
        #expect((saved["jobs"] as? [String])?.contains("find-where-readers-disagree") == true)
        #expect(saved["languages"] as? [String] == ["la"])
    }

    @Test("when the engine's plan does not hold the step, nothing is saved and the lens says why")
    func nothingSavedWithoutTheStep() async {
        DisagreementEngine.assembleHasStep = false
        DisagreementEngine.saved = nil
        let store = RecipeSetupStore(client: client())

        #expect(!(await store.addStep(job: DisagreementPageView.findJob)))
        #expect(DisagreementEngine.saved == nil, "the project's setup is left as it was")
        #expect(store.errorMessage != nil)
        DisagreementEngine.assembleHasStep = true
    }

    @Test("the lens offers the step by its name in the menus")
    func offerName() {
        #expect(DisagreementPageView.findTitle == "Find Where the Readers Disagree")
        #expect(DisagreementPageView.findJob == "find-where-readers-disagree")
    }
}
