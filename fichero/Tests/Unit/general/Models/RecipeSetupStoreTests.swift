//
//  RecipeSetupStoreTests.swift
//  FicheroTests
//
//  Setup's store (source.onboard.*): the app sends the answers to the engine and
//  shows what the rules gave back; it never decides a step itself. These tests
//  drive the store through the generated client against a stub scoped to
//  /api/recipes, so they never race other suites' requests (#4024).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class RecipesMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?
    /// What the last request carried, and how many reached the stub.
    nonisolated(unsafe) static var lastBody: [String: Any] = [:]
    nonisolated(unsafe) static var calls = 0
    nonisolated(unsafe) static var status = 200
    override static func canInit(with request: URLRequest) -> Bool {
        let path = request.url?.path ?? ""
        return path.contains("/api/recipes") || path.hasPrefix("/api/topics")
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        guard let handler = RecipesMockURLProtocol.requestHandler else {
            client?.urlProtocol(self, didFailWithError: URLError(.notConnectedToInternet)); return }
        do { let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data); client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}

@MainActor
@Suite(.serialized)
struct RecipeSetupStoreTests {

    private func makeStore(
        handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> RecipeSetupStore {
        RecipesMockURLProtocol.requestHandler = handler
        RecipesMockURLProtocol.lastBody = [:]
        RecipesMockURLProtocol.calls = 0
        RecipesMockURLProtocol.status = 200
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [RecipesMockURLProtocol.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://test.fichero")!,
            libraryPath: "/tmp/test.fichero",
            session: URLSession(configuration: configuration)
        )
        return RecipeSetupStore(client: client)
    }

    private static func reply(_ request: URLRequest, _ status: Int, _ json: String) -> (HTTPURLResponse, Data) {
        let response = HTTPURLResponse(
            url: request.url!, statusCode: status, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
        return (response, Data(json.utf8))
    }

    private static let recipeJSON = """
    {"id":"generated","title":"Spanish handwriting","purposes":["transcribe"],
     "steps":[
       {"id":"lines","job":"find-lines","model":{"kraken":"blla"},"runs_on":"this-mac",
        "reasons":["ships inside the app"],"layer":"lines"},
       {"id":"correct","job":"correct","gap":"no local corrector knows es","reasons":[]}],
     "gaps":["correct: no local corrector knows es"],"problems":[]}
    """

    /// WHY: the engine decides the recipe by rule from the answers
    /// (source.onboard.deterministic-recipe). If the store stopped sending an
    /// answer, or sent cloud consent the person never gave, the recipe shown
    /// would rest on answers nobody gave; and if it dropped the steps' reasons
    /// and gaps, setup could not say why a step is there or what is missing.
    @Test("assemble sends the answers and keeps each step's reasons and gaps")
    func assembleSendsAnswersAndKeepsReasonsAndGaps() async throws {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        let store = makeStore { request in
            #expect(request.url?.path == "/api/recipes/assemble")
            #expect(request.httpMethod == "POST")
            RecipesMockURLProtocol.lastBody = (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
            return Self.reply(request, 200, Self.recipeJSON)
        }
        store.purposes = ["transcribe"]
        store.languages = ["es"]
        store.scripts = ["Latn"]
        store.pages = 1200

        await store.assemble()

        #expect(RecipesMockURLProtocol.lastBody["purposes"] as? [String] == ["transcribe"])
        #expect(RecipesMockURLProtocol.lastBody["languages"] as? [String] == ["es"])
        #expect(RecipesMockURLProtocol.lastBody["scripts"] as? [String] == ["Latn"])
        #expect(RecipesMockURLProtocol.lastBody["pages"] as? Int == 1200)
        #expect(RecipesMockURLProtocol.lastBody["cloud_allowed"] as? Bool == false, "nothing leaves this Mac unless the person said so")
        let recipe = try #require(store.recipe)
        #expect(recipe.steps.map(\.job) == ["find-lines", "correct"])
        #expect(recipe.steps.first?.reasons == ["ships inside the app"])
        #expect(recipe.steps.last?.gap == "no local corrector knows es")
        #expect(recipe.gaps == ["correct: no local corrector knows es"])
        #expect(store.errorMessage == nil)
    }

    /// WHY (source.onboard.widget-and-search): setup's language search is the engine's catalogue,
    /// ISO 639-3 with Glottolog. A dialect must keep its language's tag and say whose dialect it is;
    /// a language only Glottolog knows has no BCP 47 tag and must not be dropped or given a wrong one.
    @Test("language search keeps a dialect's language and a Glottolog-only language's code")
    func languageSearchKeepsDialectsAndGlottologOnlyLanguages() async throws {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        let store = makeStore { request in
            #expect(request.url?.path == "/api/recipes/languages")
            #expect(request.url?.query?.contains("q=andean") == true)
            return Self.reply(request, 200, """
            {"items":[{"code":"es","name":"Andean Spanish","glottocode":"ande1249","level":"dialect","language":"Spanish"},
                      {"code":null,"name":"Kakataibo","glottocode":"kaka1265","level":"language","language":null}],
             "count":2}
            """)
        }

        let found = await store.searchLanguages("andean")

        #expect(found.map(\.code) == ["es", "und-x-kaka1265"])
        #expect(found.first?.detail == "dialect of Spanish · Glottolog ande1249")
        #expect(store.errorMessage == nil)
    }

    /// WHY (source.onboard.derives-not-asks): direction and fonts are worked out, not asked. If the
    /// store dropped what the engine derived, setup would ask about Syriac's direction or show it
    /// in a font without its letters.
    @Test("the facts derived for each chosen script are kept by script")
    func derivedFactsAreKeptByScript() async throws {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        let store = makeStore { request in
            #expect(request.url?.path == "/api/recipes/derived")
            #expect(request.url?.query?.removingPercentEncoding?.contains("scripts=Syrc,Jpan") == true)
            return Self.reply(request, 200, """
            {"scripts":[
               {"script":"Syrc","direction":"rtl","direction_from":"worked out from the script (Syrc)",
                "may_be_vertical":false,"font":"Noto Sans Syriac","font_from":"Fichero's bundled Noto Sans Syriac (SIL OFL)"},
               {"script":"Jpan","direction":"ltr","direction_from":"worked out from the script (Jpan)",
                "may_be_vertical":true,"font":null,"font_from":"the system font draws it"}],
             "mac":{"chip":"Apple M1","memory_gb":16,"from":"sysctl"},"keys":[],
             "targets":[{"id":"this-mac","title":"This Mac","from":"always"}]}
            """)
        }
        store.scripts = ["Syrc", "Jpan"]

        await store.loadDerived()

        #expect(store.derivedScripts["Syrc"]?.direction == "rtl")
        #expect(store.derivedScripts["Syrc"]?.font == "Noto Sans Syriac")
        #expect(store.derivedScripts["Jpan"]?.mayBeVertical == true)
    }

    /// WHY: a step is named by the job registry, keyed by the step's job id
    /// (its explanation is the topic registry's: TopicStoreTests). If the store
    /// did not key the registry by id, setup would show bare ids; if it invented
    /// an entry for an unregistered job, it would name a tool that does not exist.
    @Test("a step's name comes from the job registry")
    func stepNameComesFromRegistry() async throws {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        let store = makeStore { request in
            if request.url?.path == "/api/recipes/jobs" {
                return Self.reply(request, 200, """
                {"count":1,"items":[{"id":"find-lines","name":"Find lines",
                 "description":"Finds each line of writing on the page.","topic":"find-lines","layer":"lines",
                 "takes":["image"],"gives":["lines"],"compare":"line boxes","settings":[],"since":"0.1"}]}
                """)
            }
            if request.url?.path == "/api/topics" {
                return Self.reply(request, 200, #"{"items":[],"count":0}"#)
            }
            return Self.reply(request, 200, Self.recipeJSON)
        }
        store.languages = ["es"]
        store.scripts = ["Latn"]

        await store.loadJobs()
        await store.assemble()

        let steps = try #require(store.recipe?.steps)
        #expect(store.job(for: steps[0])?.name == "Find lines")
        #expect(store.job(for: steps[1]) == nil, "an unregistered job is shown as unknown, never invented")
    }

    /// WHY: without a language and a script the engine refuses (422); the store
    /// must not call it, and a refusal it does get must surface as an error with
    /// no stale recipe left on screen as if it were the answer.
    @Test("no call without languages and scripts; a refusal clears the recipe")
    func refusalSurfacesAndClearsRecipe() async throws {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        let store = makeStore { request in
            RecipesMockURLProtocol.calls += 1
            return RecipesMockURLProtocol.status == 200
                ? Self.reply(request, 200, Self.recipeJSON)
                : Self.reply(request, 422, #"{"detail":[{"loc":["body","purpose"],"msg":"bad","type":"value_error"}]}"#)
        }

        await store.assemble()
        #expect(RecipesMockURLProtocol.calls == 0, "the engine requires a language and a script; setup asks for them first")

        store.languages = ["es"]
        store.scripts = ["Latn"]
        await store.assemble()
        #expect(store.recipe != nil)

        RecipesMockURLProtocol.status = 422
        await store.assemble()
        #expect(store.recipe == nil, "a refused answer must not leave the previous recipe standing")
        #expect(store.errorMessage != nil)
    }

    /// WHY: the purposes setup offers are the engine's (one list for setup, the
    /// CLI and MCP). If the store reordered them, dropped the description, or
    /// lost which ones run by themselves, setup would offer a purpose the
    /// engine does not know or promise automatic work that will not happen.
    @Test("purposes load from the engine, in its order, with descriptions")
    func purposesLoadFromEngine() async throws {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        let store = makeStore { request in
            #expect(request.url?.path == "/api/recipes/purposes")
            RecipesMockURLProtocol.calls += 1
            return Self.reply(request, 200, """
            {"count":2,"items":[
              {"id":"transcribe","title":"Just transcribe","description":"Lines and readings.","runs_by_itself":true},
              {"id":"not-sure","title":"Not sure yet","description":"Everything on demand.","runs_by_itself":false}]}
            """)
        }

        await store.loadPurposes()
        await store.loadPurposes()

        #expect(store.purposeOptions.map(\.id) == ["transcribe", "not-sure"])
        #expect(store.purposeOptions.first?.description == "Lines and readings.")
        #expect(store.purposeOptions.map(\.runsByItself) == [true, false])
        #expect(RecipesMockURLProtocol.calls == 1, "the list is loaded once and kept")
    }

    /// WHY: egress is asked only when a cloud model would fit a step
    /// (source.onboard.cloud-asked-once). Asking when nothing could use the
    /// cloud is a needless question; not asking when something could hides a
    /// choice. Once the person said yes, the question stays so it can be undone.
    @Test("the cloud question follows the recipe's cloud options")
    func cloudQuestionFollowsCloudOptions() async throws {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        let store = makeStore { request in
            RecipesMockURLProtocol.status == 200
                ? Self.reply(request, 200, Self.recipeJSON)
                : Self.reply(request, 200, Self.recipeJSON.replacingOccurrences(
                    of: #""problems":[]"#, with: #""cloud_options":["correct"],"problems":[]"#))
        }
        store.languages = ["es"]
        store.scripts = ["Latn"]

        await store.assemble()
        #expect(store.asksCloudQuestion == false, "no cloud option: everything runs on this Mac")

        RecipesMockURLProtocol.status = 201   // any non-200 marker: serve the cloud-option recipe
        await store.assemble()
        #expect(store.recipe?.cloudOptions == ["correct"])
        #expect(store.asksCloudQuestion)

        RecipesMockURLProtocol.status = 200
        store.cloudAllowed = true
        await store.assemble()
        #expect(store.asksCloudQuestion, "a yes already given stays answerable")
    }

    /// WHY: sources are linked by default, so files stay where they are
    /// (ruled 2026-10-03). A copy or move default would duplicate or relocate a
    /// person's files on their first import without them choosing it.
    @Test("sources are linked by default")
    func intakeDefaultsToLink() {
        let store = makeStore { request in Self.reply(request, 200, "{}") }
        #expect(store.ingestMode == .link)
    }

    /// WHY: first run and Set Up… reopen where the person left off. If loading
    /// dropped an answer, mapped the engine's lowercase ingest mode wrongly, or
    /// lost the saved recipe, reopening setup would silently change what the
    /// person chose, most dangerously turning "copy" back into another mode.
    @Test("loading the project's setup fills the answers, import choice and recipe")
    func loadSavedFillsAnswersAndRecipe() async throws {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        let store = makeStore { request in
            #expect(request.url?.path == "/api/recipes/project")
            #expect(request.httpMethod == "GET")
            return Self.reply(request, 200, """
            {"answers":{"purpose":"entities","languages":["es","la"],"scripts":["Latn"],
              "material":"print","pages":40,"cloud_allowed":true,"ingest_mode":"copy"},
             "recipe":\(Self.recipeJSON)}
            """)
        }

        await store.loadSaved()

        #expect(store.purposes == ["entities"], "a project saved with one purpose reads as a list of one")
        #expect(store.languages == ["es", "la"])
        #expect(store.scripts == ["Latn"])
        #expect(store.materials == ["print"])
        #expect(store.pages == 40)
        #expect(store.cloudAllowed)
        #expect(store.ingestMode == .copy)
        #expect(store.recipe?.steps.map(\.job) == ["find-lines", "correct"])
        #expect(store.errorMessage == nil)
    }

    /// WHY: a project with nothing saved behaves as today (source.onboard.set-up-later):
    /// the defaults stay, link included, and no error is shown.
    @Test("nothing saved leaves the defaults")
    func loadSavedWithNothingKeepsDefaults() async throws {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        let store = makeStore { request in Self.reply(request, 200, #"{"answers":null,"recipe":null}"#) }

        await store.loadSaved()

        #expect(store.purposes == ["transcribe"])
        #expect(store.ingestMode == .link)
        #expect(store.recipe == nil)
        #expect(store.errorMessage == nil)
    }

    /// WHY: saving writes the answers under the engine's field names, with the
    /// ingest mode in the engine's lowercase form, plus the proposed recipe. A
    /// renamed key or an upper-case "MOVE" would be saved but never read back
    /// the same, and the first import could use the wrong mode.
    @Test("save sends the answers and the recipe under the engine's names")
    func saveSendsAnswersAndRecipe() async throws {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        let store = makeStore { request in
            if request.url?.path == "/api/recipes/project" {
                #expect(request.httpMethod == "PUT")
                RecipesMockURLProtocol.lastBody =
                    (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
                return Self.reply(request, 200, #"{"answers":{},"recipe":null}"#)
            }
            return Self.reply(request, 200, Self.recipeJSON)
        }
        store.languages = ["es"]
        store.scripts = ["Latn"]
        store.ingestMode = .move
        await store.assemble()

        let saved = await store.save()

        #expect(saved)
        let answers = try #require(RecipesMockURLProtocol.lastBody["answers"] as? [String: Any])
        #expect(answers["purposes"] as? [String] == ["transcribe"])
        #expect(answers["languages"] as? [String] == ["es"])
        #expect(answers["scripts"] as? [String] == ["Latn"])
        #expect(answers["cloud_allowed"] as? Bool == false)
        #expect(answers["ingest_mode"] as? String == "move")
        let recipe = try #require(RecipesMockURLProtocol.lastBody["recipe"] as? [String: Any])
        #expect(recipe["id"] as? String == "generated")
        #expect((recipe["steps"] as? [Any])?.count == 2)
    }

    /// WHY: the engine refuses a setup that holds keys or code (422). The
    /// person must see that it was not saved, not believe it was.
    @Test("a refused save says so")
    func refusedSaveSaysSo() async throws {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        let store = makeStore { request in
            Self.reply(request, 422, #"{"detail":[{"loc":["body","answers"],"msg":"holds a key","type":"value_error"}]}"#)
        }

        let saved = await store.save()

        #expect(saved == false)
        #expect(store.errorMessage != nil)
    }
    private static func planJSON(refusals: String) -> String {
        """
        {"runs":[],"skipped":[],"workflows":[{"steps":["find-lines","read-a-line"],"job":"read-a-line","workflow":"Transcribe (Kraken)",
          "workflow_id":"w1","runs_on":"this-mac"}],
         "offered":["train-a-model"],"refusals":[\(refusals)],
         "estimate":{"pages":49,"runs":[],"total_cost_usd":null}}
        """
    }

    /// WHY: nothing in a project runs before the person's first yes, and the engine, not the
    /// app, decides whether Start can go (source.project.automatic-after-first-yes). If the store
    /// offered Start while a step was refused, the person would press Start on a plan the engine
    /// already said it cannot run; a missing price must stay unknown, never read as free.
    @Test("Start is offered only for a plan with nothing refused; an unpriced total stays unknown")
    func startNeedsAPlanWithNoRefusals() async {
        let refused = makeStore { request in
            Self.reply(request, 200, Self.planJSON(refusals: "\"correct: no model fits\""))
        }
        await refused.loadStartPlan()
        #expect(refused.startPlan?.refusals == ["correct: no model fits"])
        #expect(refused.canStart == false)

        let clear = makeStore { request in Self.reply(request, 200, Self.planJSON(refusals: "")) }
        await clear.loadStartPlan()
        #expect(clear.canStart)
        #expect(clear.startPlan?.estimate.totalCostUsd == nil)
        #expect(RecipeStartFields.cost(nil) == "price unknown")
    }

    /// WHY: Start must record the yes in the engine (POST, audited) before the window closes; a
    /// refusal must not close it, and must say so.
    @Test("start posts the yes; a refusal returns false and says so")
    func startPostsTheYes() async {
        let store = makeStore { request in
            RecipesMockURLProtocol.calls += 1
            if request.httpMethod == "POST" {
                return Self.reply(request, RecipesMockURLProtocol.status, RecipesMockURLProtocol.status == 200
                    ? Self.planJSON(refusals: "") : #"{"detail":[]}"#)
            }
            return Self.reply(request, 200, Self.planJSON(refusals: "\"read-a-line: no reader\""))
        }
        #expect(await store.start())

        RecipesMockURLProtocol.status = 422
        #expect(await store.start() == false)
        #expect(store.errorMessage != nil)
    }
}

/// `URLRequest.httpBody` is nil once the request has gone through
/// `URLProtocol` (the body moves to `httpBodyStream`). Shared with `RecipeSetupFlowTests`.
extension URLRequest {
    func bodyOrStream() -> Data {
        if let httpBody { return httpBody }
        guard let stream = httpBodyStream else { return Data() }
        stream.open()
        defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let read = stream.read(&buffer, maxLength: buffer.count)
            if read <= 0 { break }
            data.append(buffer, count: read)
        }
        return data
    }

}
