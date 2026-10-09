//
//  SetupRulingsOctNineTests.swift
//  FicheroTests
//
//  The maintainer's setup test notes of 2026-10-09 (`source/models-chains-and-projects.md` section 7b):
//  the goals ordered and grouped (#5625, `source.onboard.purposes-grouped`), a language proposing its usual
//  script (#5626, `source.onboard.script-from-language`), and the plan on Ready edited by taking steps out
//  (#5627, `source.onboard.plan-editable`). Through the real `RecipeSetupStore` over the generated client;
//  only the transport is stubbed, on this suite's own session.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class OctNineURLProtocol: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) -> (Int, String))?
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
struct SetupRulingsOctNineTests {

    private func makeStore(_ handler: @escaping (URLRequest) -> (Int, String)) -> RecipeSetupStore {
        OctNineURLProtocol.handler = handler
        OctNineURLProtocol.seen = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [OctNineURLProtocol.self]
        return RecipeSetupStore(client: FicheroClient(baseURL: URL(string: "https://test.fichero")!,
                                                      libraryPath: "/tmp/oct-nine.fichero",
                                                      session: URLSession(configuration: configuration)))
    }

    /// `GET /api/recipes/purposes` as the engine orders and groups them (#5625).
    private static let purposesJSON = """
    {"count":4,"items":[
     {"id":"transcribe","title":"Transcribe","description":"Lines and readings.","runs_by_itself":true,
      "jobs":[{"id":"find-lines","title":"Find lines"},{"id":"read-a-line","title":"Read each line"},
              {"id":"correct","title":"Correct"}]},
     {"id":"search","title":"Search","description":"By meaning.","runs_by_itself":true,"parent":"transcribe",
      "jobs":[{"id":"find-lines","title":"Find lines"},{"id":"read-a-line","title":"Read each line"},
              {"id":"correct","title":"Correct"},{"id":"make-a-vector","title":"Make it searchable"}]},
     {"id":"knowledge-graph","title":"Knowledge graph","description":"One graph.","runs_by_itself":true,
      "jobs":[{"id":"find-lines","title":"Find lines"},{"id":"read-a-line","title":"Read each line"},
              {"id":"correct","title":"Correct"},{"id":"find-names-tag-words","title":"Find names"},
              {"id":"make-a-vector","title":"Make it searchable"}]},
     {"id":"entities","title":"Entities","description":"Names.","runs_by_itself":true,"parent":"knowledge-graph",
      "jobs":[{"id":"find-lines","title":"Find lines"},{"id":"read-a-line","title":"Read each line"},
              {"id":"correct","title":"Correct"},{"id":"find-names-tag-words","title":"Find names"}]}]}
    """

    /// A plan whose first step a later one needs, and one step already taken out.
    private static let recipeJSON = """
    {"id":"generated","title":"t","purposes":["transcribe"],"gaps":[],"problems":[],
     "steps":[{"id":"find-lines","job":"find-lines","title":"Find lines","reasons":[],"needed_by":["read-a-line"]},
              {"id":"read-a-line","job":"read-a-line","title":"Read each line","reasons":[],
               "needed_by":["correct"]},
              {"id":"correct","job":"correct","title":"Correct","reasons":[]}],
     "removed":[{"job":"make-a-vector","title":"Make it searchable"}]}
    """

    private func purposeStore() async -> RecipeSetupStore {
        let store = makeStore { request in
            switch request.url?.path {
            case "/api/recipes/purposes": (200, Self.purposesJSON)
            case "/api/recipes/assemble": (200, Self.recipeJSON)
            default: (200, #"{"answers":{},"recipe":null}"#)
            }
        }
        await store.loadPurposes()
        store.purposes = []
        return store
    }

    // MARK: #5625, the goals grouped

    /// WHY: "The full knowledge graph", "Statements" and "Entities" read as three look-alike goals. Listed under
    /// the graph, an option the ticked graph already includes shows ticked and fixed, saying so; the same
    /// option ticked on its own (Entities without the graph) stays possible.
    @Test("an option the ticked knowledge graph holds shows as included in it")
    func optionIncludedByTheGraph() async {
        let store = await purposeStore()
        #expect(store.purposeOptions.map(\.id) == ["transcribe", "search", "knowledge-graph", "entities"],
                "the engine's order, an option after the purpose it is listed under")
        #expect(store.includingPurpose(of: "entities") == nil, "nothing ticked includes nothing")

        store.toggle(purpose: "knowledge-graph")
        #expect(store.includingPurpose(of: "entities")?.id == "knowledge-graph")

        store.toggle(purpose: "transcribe")
        #expect(store.includingPurpose(of: "search") == nil,
                "Transcribe does not make the text searchable, so Search under it is still a choice")

        store.toggle(purpose: "knowledge-graph")
        store.toggle(purpose: "entities")
        #expect(store.includingPurpose(of: "entities") == nil, "ticked on its own, it is its own")
    }

    // MARK: #5626, a language proposes its usual script

    /// WHY: a person who names English was then asked for its script, which Fichero knows. The language's
    /// usual script is put in for them; one the person chose stays theirs; a language taken out takes out only
    /// the script it alone proposed.
    @Test("a language puts in its usual script; taking the language out takes only that script")
    func languageProposesItsScript() {
        let store = makeStore { _ in (200, "{}") }
        store.add(.init(code: "en", name: "English", detail: nil, usualScript: "Latn", usualScriptName: "Latin"),
                  toScripts: false)
        #expect(store.scripts == ["Latn"] && store.name(of: "Latn") == "Latin")
        #expect(store.proposedScripts.keys.sorted() == ["Latn"])

        store.add(.init(code: "ru", name: "Russian", detail: nil, usualScript: "Cyrl", usualScriptName: "Cyrillic"),
                  toScripts: false)
        store.add(.init(code: "la", name: "Latin", detail: nil, usualScript: "Latn", usualScriptName: "Latin"),
                  toScripts: false)
        #expect(store.scripts == ["Latn", "Cyrl"], "a script already there is not added twice")

        store.remove("ru", fromScripts: false)
        #expect(store.scripts == ["Latn"], "Cyrillic came only from Russian")
        store.remove("en", fromScripts: false)
        #expect(store.scripts == ["Latn"], "Latin is still proposed by Latin")

        let chosen = makeStore { _ in (200, "{}") }
        chosen.add(.init(code: "Latn", name: "Latin", detail: nil), toScripts: true)
        chosen.add(.init(code: "en", name: "English", detail: nil, usualScript: "Latn", usualScriptName: "Latin"),
                   toScripts: false)
        chosen.remove("en", fromScripts: false)
        #expect(chosen.scripts == ["Latn"], "a script the person chose is never taken out with a language")

        let unknown = makeStore { _ in (200, "{}") }
        unknown.add(.init(code: "und-x-abcd1234", name: "Some languoid", detail: nil), toScripts: false)
        #expect(unknown.scripts.isEmpty, "no usual script on record proposes nothing")
    }

    /// WHY: the script comes from the engine's language search (CLDR likely subtags), never a table in the app.
    @Test("a language match carries the engine's usual script")
    func searchCarriesTheScript() async {
        let store = makeStore { request in
            request.url?.path == "/api/recipes/languages"
                ? (200, #"{"count":1,"items":[{"code":"en","name":"English","level":"language","script":"Latn","script_name":"Latin"}]}"#)
                : (404, "{}")
        }
        let found = await store.searchLanguages("english")
        #expect(found.first?.usualScript == "Latn" && found.first?.usualScriptName == "Latin")
    }

    // MARK: #5627, the plan on Ready can be edited

    /// WHY: a step a later one needs cannot go (the plan would fail its own check at Start), and Ready says
    /// which step needs it; the last step can always go.
    @Test("only a step nothing needs can be taken out, and Ready says what needs it")
    func whatCanBeTakenOut() async throws {
        let store = await purposeStore()
        store.languages = ["es"]
        store.scripts = ["Latn"]
        await store.assemble()
        let steps = try #require(store.recipe?.steps)
        #expect(steps.map(RecipeSetupStore.canTakeOut) == [false, false, true])
        #expect(RecipeStepsView.neededSentence(steps[0], store: store) == "Read each line needs it, so it stays.")
        #expect(store.recipe?.removed?.map(\.job) == ["make-a-vector"], "what was taken out is offered back")
    }

    /// WHY: taking a step out is an answer: the engine is asked for the plan without it, and the answer is saved
    /// with the project, so Set Up… reopens with it and Start runs the edited plan. Putting it back, or ticking
    /// a purpose that brings it, asks for it again.
    @Test("a step taken out is sent and saved as removed_jobs; put back or re-ticked, it returns")
    func takeOutIsSentAndSaved() async throws {
        let store = await purposeStore()
        store.languages = ["es"]
        store.scripts = ["Latn"]
        store.toggle(purpose: "transcribe")

        await store.takeOut(job: "correct")
        let asked = try #require(OctNineURLProtocol.seen.last { $0.path == "/api/recipes/assemble" })
        #expect(asked.body["removed_jobs"] as? [String] == ["correct"])
        #expect(await store.save())
        let answers = try #require(OctNineURLProtocol.seen.last { $0.method == "PUT" }?.body["answers"] as? [String: Any])
        #expect(answers["removed_jobs"] as? [String] == ["correct"])

        await store.putBack(job: "correct")
        #expect(store.removedJobs.isEmpty)
        let again = try #require(OctNineURLProtocol.seen.last { $0.path == "/api/recipes/assemble" })
        #expect(again.body["removed_jobs"] == nil, "nothing taken out sends nothing")

        await store.takeOut(job: "make-a-vector")
        store.toggle(purpose: "search")
        #expect(store.removedJobs.isEmpty, "ticking Search asks for its step again")
    }
}
