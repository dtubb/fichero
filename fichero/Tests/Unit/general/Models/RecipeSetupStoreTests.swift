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
    /// What the last request to each path carried (by path, so a stray request to another path
    /// cannot overwrite the one a test reads), and how many reached the stub.
    nonisolated(unsafe) static var bodies: [String: [String: Any]] = [:]
    nonisolated(unsafe) static var calls = 0
    nonisolated(unsafe) static var status = 200
    override static func canInit(with request: URLRequest) -> Bool {
        let path = request.url?.path ?? ""
        // Training from Ready (#5660 item 9) posts its action through the audited choke point.
        return path.contains("/api/recipes") || path.hasPrefix("/api/topics") || path == "/api/actions/invoke"
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
        RecipesMockURLProtocol.bodies = [:]
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
    @Test("a recipe whose overrides are null is read without ending the app")
    func nullOverridesDoNotCrash() {
        let store = makeStore { request in Self.reply(request, 404, "{}") }
        // `"overrides": null` once raised an Objective-C exception in JSONSerialization (2026-10-10).
        store.adoptEngineRecipe(Data(#"{"overrides": null}"#.utf8))
        store.adoptEngineRecipe(Data(#"{"overrides": "x"}"#.utf8))
        #expect(store.errorMessage != nil)
    }

    @Test("assemble sends the answers and keeps each step's reasons and gaps")
    func assembleSendsAnswersAndKeepsReasonsAndGaps() async throws {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        let store = makeStore { request in
            #expect(request.url?.path == "/api/recipes/assemble")
            #expect(request.httpMethod == "POST")
            RecipesMockURLProtocol.bodies["/api/recipes/assemble"] =
                (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
            return Self.reply(request, 200, Self.recipeJSON)
        }
        store.purposes = ["transcribe"]
        store.languages = ["es"]
        store.scripts = ["Latn"]
        store.pages = 1200

        await store.assemble()

        let sent = RecipesMockURLProtocol.bodies["/api/recipes/assemble"] ?? [:]
        #expect(sent["purposes"] as? [String] == ["transcribe"])
        #expect(sent["languages"] as? [String] == ["es"])
        #expect(sent["scripts"] as? [String] == ["Latn"])
        #expect(sent["pages"] as? Int == 1200)
        #expect(sent["cloud_allowed"] as? Bool == false, "nothing leaves this Mac unless the person said so")
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
                    of: #""problems":[]"#, with: #""cloud_options":["correct"],"cloud_offer":[{"job":"correct","title":"Correct","sends":"the text of the pages","to":"google","pages":3000,"cost_usd":4.5,"sentence":"Correct: would send the text of 3,000 pages to google, about $4.50."}],"problems":[]"#))
        }
        store.languages = ["es"]
        store.scripts = ["Latn"]

        await store.assemble()

        RecipesMockURLProtocol.status = 201   // any non-200 marker: serve the cloud-option recipe
        await store.assemble()
        #expect(store.recipe?.cloudOptions == ["correct"])
        #expect(store.cloudOfferSentences == ["Correct: would send the text of 3,000 pages to google, about $4.50."],
                "the question shows what is sent, to whom, how many pages and the estimate, in the engine's words")
    }

    /// WHY: sources are copied by default (section 7d): the originals are never touched and the
    /// project owns its files. A move default would relocate a person's files unasked.
    @Test("sources are copied by default")
    func intakeDefaultsToCopy() {
        let store = makeStore { request in Self.reply(request, 200, "{}") }
        #expect(store.ingestMode == .copy)
    }

    /// WHY: first run and Set Up… reopen where the person left off. If loading
    /// dropped an answer, mapped the engine's lowercase ingest mode wrongly, or
    /// lost the saved recipe, reopening setup would silently change what the
    /// person chose, most dangerously turning "copy" back into another mode.
    @Test("loading the project's setup fills the answers, import choice and recipe")
    func loadSavedFillsAnswersAndRecipe() async throws {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        let store = makeStore { request in
            #expect(request.httpMethod == "GET")
            // The saved tags are named from the engine's search (`resolveNames`), as a pick names them.
            switch request.url?.path {
            case "/api/recipes/languages":
                let code = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?
                    .queryItems?.first { $0.name == "q" }?.value ?? ""
                let name = ["es": "Spanish", "la": "Latin"][code] ?? code
                return Self.reply(request, 200, #"{"items":[{"code":"\#(code)","name":"\#(name)","level":"language"}],"count":1}"#)
            case "/api/recipes/scripts":
                return Self.reply(request, 200, #"{"items":[{"code":"Latn","name":"Latin"}],"count":1}"#)
            default:
                #expect(request.url?.path == "/api/recipes/project")
            }
            return Self.reply(request, 200, """
            {"answers":{"purpose":"entities","languages":["es","la"],"scripts":["Latn"],
              "material":"print","pages":40,"cloud_allowed":true,"ingest_mode":"copy"},
             "recipe":\(Self.recipeJSON)}
            """)
        }

        await store.loadSaved()

        #expect(store.name(of: "es") == "Spanish" && store.name(of: "la") == "Latin" && store.name(of: "Latn") == "Latin",
                "a reopened project shows its languages and script by name")

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

    /// WHY (2026-10-11): naming the saved tags is a nicety on top of answers that loaded fine; if the search
    /// fails, the field shows the codes and setup shows no error.
    @Test("a failed name lookup on load leaves the codes and says nothing")
    func failedNameLookupIsQuiet() async throws {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        let store = makeStore { request in
            if request.url?.path == "/api/recipes/project" {
                return Self.reply(request, 200, """
                {"answers":{"purpose":"transcribe","languages":["es"],"scripts":["Latn"]},"recipe":null}
                """)
            }
            return Self.reply(request, 500, #"{"detail":"search is down"}"#)
        }

        await store.loadSaved()

        #expect(store.languages == ["es"] && store.scripts == ["Latn"])
        #expect(store.name(of: "es") == "es" && store.name(of: "Latn") == "Latn", "the codes show")
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
        #expect(store.ingestMode == .copy)
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
                RecipesMockURLProtocol.bodies["/api/recipes/project"] =
                    (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
                return Self.reply(request, 200, #"{"answers":{},"recipe":null}"#)
            }
            return Self.reply(request, 200, Self.recipeJSON)
        }
        store.languages = ["es"]
        store.scripts = ["Latn"]
        store.ingestMode = .move
        store.cloudChoice = false  // the person answered "no": an unanswered question is not saved (inherits the app's)
        await store.assemble()

        let saved = await store.save()

        #expect(saved)
        let savedBody = RecipesMockURLProtocol.bodies["/api/recipes/project"] ?? [:]
        let answers = try #require(savedBody["answers"] as? [String: Any])
        #expect(answers["purposes"] as? [String] == ["transcribe"])
        #expect(answers["languages"] as? [String] == ["es"])
        #expect(answers["scripts"] as? [String] == ["Latn"])
        #expect(answers["cloud_allowed"] as? Bool == false)
        #expect(answers["ingest_mode"] as? String == "move")
        let recipe = try #require(savedBody["recipe"] as? [String: Any])
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
    /// WHY (#5660 item 1, the maintainer's Set Up test of 2026-10-10): "Into what" was one choice, but a person may
    /// want the page as written, with abbreviations expanded and in normalised spelling, each its own reading. The
    /// answer is a list in the engine's spelling, a translation is one more item, and a project saved with one
    /// value reopens with that one ticked.
    @Test("Into what is several levels and a translation; a single saved value reads as one ticked")
    func intoWhatIsAMultiSelect() throws {
        typealias Answers = RecipeSetupAnswers.JobAnswers
        let old = try JSONDecoder().decode(Answers.self, from: Data(#"{"normalise_how_far":"normalised"}"#.utf8))
        #expect(old.normaliseHowFar == ["regularised"])
        #expect(old.writes(level: "regularised"))

        var answers = Answers()
        #expect(answers.normaliseHowFar == ["expanded"], "the default")
        answers.set(level: "as_written", true)
        answers.translation = "en"
        answers.set(level: "modernised", true)
        answers.set(level: "expanded", false)
        #expect(answers.normaliseHowFar == ["as_written", "modernised", "translation:en"], "cascade order, then the translation")
        #expect(answers.translation == "en")
        answers.translation = nil
        #expect(answers.normaliseHowFar == ["as_written", "modernised"])

        let sent = try JSONSerialization.jsonObject(with: JSONEncoder().encode(answers)) as? [String: Any]
        #expect(sent?["normalise_how_far"] as? [String] == ["as_written", "modernised"], "sent as a list")
        let saved = try JSONDecoder().decode(Answers.self, from: Data(
            #"{"normalise_how_far":["as-written","expanded","translation:es"]}"#.utf8))
        #expect(saved.normaliseHowFar == ["as_written", "expanded", "translation:es"])
        #expect(RecipeSetupAnswers.JobAnswers.normaliseLevels.map(\.title)
                == ["As written", "Abbreviations expanded", "Normalised spelling", "Modernised"])
    }

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

    /// WHY (#5616): a step the last run did not finish runs again at Start; Ready says so under the step, with
    /// why, so the person is not surprised it runs again (and knows why it did not before).
    @Test("Ready says what the last run left undone under the step, and that it runs again")
    func readySaysWhatTheLastRunLeft() async {
        let plan = """
        {"runs":[{"steps":["lines","read"],"job":"read-a-line","card":"workflow","runs_on":"this-mac",
                  "last_run":"not run","last_why":"the run was stopped before this step"},
                 {"steps":["names"],"job":"find-names-tag-words","card":"workflow","runs_on":"this-mac"}],
         "skipped":[],"workflows":[],"offered":[],"refusals":[],
         "estimate":{"pages":92,"runs":[],"total_cost_usd":null}}
        """
        let store = makeStore { request in Self.reply(request, 200, plan) }
        await store.loadStartPlan()

        #expect(store.lastRunWords(stepId: "read") == "Not run last time (the run was stopped before this step); runs again")
        #expect(store.lastRunWords(stepId: "lines") == store.lastRunWords(stepId: "read"), "one run, both its steps")
        #expect(store.lastRunWords(stepId: "names") == nil, "done last time, or never ran: nothing said")
        #expect(store.lastRunWords(stepId: "missing") == nil)
    }

    /// `source.onboard.setup-says-what-is-happening` (#5791): a download under way and a no-model step show the
    /// engine's own sentences (`StartDownload.sentence`, `StartRun.how`), not words the app composes.
    @Test("Ready shows the engine's download sentence and a rules step's how")
    func readyShowsTheEnginesSentences() async throws {
        let plan = """
        {"runs":[{"steps":["dates"],"job":"work-out-dates","card":"workflow","runs_on":"this-mac","how":"Rules, not a model: it reads the date at the head of each page."}],
         "skipped":[],"workflows":[],"offered":[],"refusals":[],"waiting":[],
         "downloads":[{"runtime":"kraken","model":"blla","steps":["lines"],"size_mb":40,"action":"model.download",
            "params":{"runtime":"kraken","model":"blla"},"downloading":true,"progress":"12 MB of 40 MB","job_id":"j1",
            "sentence":"Downloading blla: 12 MB of 40 MB; its steps wait for it."}],
         "estimate":{"pages":92,"runs":[],"total_cost_usd":null}}
        """
        let store = makeStore { request in Self.reply(request, 200, plan) }
        await store.loadStartPlan()

        #expect(store.how(ofStep: "dates") == "Rules, not a model: it reads the date at the head of each page.")
        #expect(store.how(ofStep: "lines") == nil)
        let download = try #require(store.downloads.first, "the plan's download decoded into the store")
        #expect(RecipeDownloadRows.underWayLine(download, store: store)
                == "Downloading blla: 12 MB of 40 MB; its steps wait for it.")
    }

    /// WHY (#5660 item 6, the maintainer's Set Up test of 2026.10.10): the needed models began downloading by
    /// themselves, yet Ready kept Start disabled and said "not on this Mac: download it first". A model already
    /// downloading is not a refusal: Start stays pressable, and the plan says it is downloading, with its progress.
    @Test("Start stays pressable while a needed model downloads, and Ready says it is downloading")
    func startWhileAModelDownloads() async {
        let plan = """
        {"runs":[],"skipped":[],"workflows":[{"steps":["lines","read"],"job":"read-a-line","workflow":"Transcribe (Kraken)",
          "workflow_id":"w1","runs_on":"this-mac"}],
         "offered":[],"refusals":[],
         "waiting":["steps lines, read wait for blla, which is downloading (12 MB of 40 MB): they run when it lands"],
         "downloads":[
           {"runtime":"kraken","model":"blla","steps":["lines","read"],"size_mb":40,"action":"model.download",
            "params":{"runtime":"kraken","model":"blla"},"downloading":true,"progress":"12 MB of 40 MB","job_id":"j1"},
           {"runtime":"spacy","model":"es_core_news_sm","steps":["names"],"size_mb":13,"action":"model.download",
            "params":{"runtime":"spacy","model":"es_core_news_sm"}}],
         "start_downloads":{"items":[{"name":"the spaCy model es_core_news_sm","size_mb":13,"steps":["names"]}],
           "total_mb":13,"total_known":true,"sentence":"Start downloads the spaCy model es_core_news_sm (13 MB)."},
         "estimate":{"pages":92,"runs":[],"total_cost_usd":null}}
        """
        let store = makeStore { request in Self.reply(request, 200, plan) }
        await store.loadStartPlan()

        #expect(store.canStart, "a model downloading does not hold Start")
        #expect(store.waitingForDownloads.count == 1)
        #expect(store.waitingForDownloads.first?.contains("which is downloading") == true)
        #expect(!store.waitingForDownloads.contains { $0.contains("download it first") })
        let downloads = store.downloads
        #expect(RecipeDownloadRows.isUnderWay(downloads[0]))
        #expect(RecipeDownloadRows.engineProgress(downloads[0]) == "12 MB of 40 MB")
        #expect(!RecipeDownloadRows.isUnderWay(downloads[1]))
        #expect(RecipeDownloadRows.engineProgress(downloads[1]) == nil, "not started: Start will fetch it")
        // #5664 (ruled 2026-10-11): nobody downloads in setup. Ready says what Start will fetch, in the engine's
        // one sentence, and offers no Download button and no "To download first".
        #expect(RecipeDownloadRows.sentence(store) == "Start downloads the spaCy model es_core_news_sm (13 MB).")
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

    /// WHY (`source.recipe.folder-scoped-start`, #5540): Run the Recipe on This Folder… must plan and start
    /// the run on that folder alone, or it would run the whole archive; and Start, with no folder, must send
    /// exactly what it sent before (no query, no body), or the whole-project run would change under it.
    @Test("a folder's plan and start send folder_id; with no folder nothing changes")
    func folderPlanAndStartSendTheFolder() async {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        // Each request recorded under "<n> <method>": its query, its JSON body, and its body's size.
        let store = makeStore { request in
            RecipesMockURLProtocol.calls += 1
            let body = request.bodyOrStream()
            RecipesMockURLProtocol.bodies["\(RecipesMockURLProtocol.calls) \(request.httpMethod ?? "")"] = [
                "query": request.url?.query ?? "",
                "json": (try? JSONSerialization.jsonObject(with: body)) as? [String: Any] ?? [:],
                "bytes": body.count
            ]
            return Self.reply(request, 200, Self.planJSON(refusals: ""))
        }
        func seen(_ key: String) -> [String: Any] { RecipesMockURLProtocol.bodies[key] ?? [:] }

        await store.loadStartPlan(folderId: "folder-7")
        #expect(seen("1 GET")["query"] as? String == "folder_id=folder-7")
        #expect(store.startPlanFolderId == "folder-7")
        #expect(await store.start(folderId: "folder-7"))
        #expect((seen("2 POST")["json"] as? [String: Any])?["folder_id"] as? String == "folder-7")
        #expect(store.startPlanFolderId == "folder-7")

        await store.loadStartPlan()
        #expect(seen("3 GET")["query"] as? String == "", "the whole project: no folder in the query")
        #expect(store.startPlanFolderId == nil)
        #expect(await store.start())
        #expect(seen("4 POST")["bytes"] as? Int == 0, "the whole project's Start sends no body, as before")
        #expect(RecipesMockURLProtocol.calls == 4)
    }

    /// WHY (#5583, `source.onboard.auto.installed-model-first`): a step waiting for a model download
    /// stayed refused after the download finished until setup was opened again. The engine now says
    /// `model.installed` on the change stream; the store reads the shown plan again on it, and a
    /// store that never showed a plan asks nothing.
    @Test("model.installed reads the shown Start plan again; nothing else does")
    func modelInstalledReadsThePlanAgain() async throws {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        let store = makeStore { request in
            RecipesMockURLProtocol.calls += 1
            let refusals = RecipesMockURLProtocol.calls == 1 ? "\"read-a-line: waits for the download of blla\"" : ""
            return Self.reply(request, 200, Self.planJSON(refusals: refusals))
        }
        let installed = try JSONDecoder().decode(ChangeEvent.self, from: Data(
            #"{"type":"model.installed","actor":"system"}"#.utf8))
        let other = try JSONDecoder().decode(ChangeEvent.self, from: Data(
            #"{"type":"model.deleted","actor":"system"}"#.utf8))

        store.apply(installed)
        try await Task.sleep(for: .milliseconds(200))
        #expect(RecipesMockURLProtocol.calls == 0, "no plan shown, nothing to read again")

        await store.loadStartPlan()
        #expect(store.canStart == false)
        #expect(store.changeDomains == ["model"])

        store.apply(other)
        try await Task.sleep(for: .milliseconds(200))
        #expect(RecipesMockURLProtocol.calls == 1, "only model.installed reads the plan again")

        store.apply(installed)
        let deadline = Date().addingTimeInterval(5)
        while !store.canStart, Date() < deadline {
            try await Task.sleep(for: .milliseconds(50))
        }
        #expect(RecipesMockURLProtocol.calls == 2)
        #expect(store.canStart, "the step that waited for the model no longer waits")
    }

    /// WHY (`ai.where.fallback-free-and-asked`, #5592): a step whose model this Mac cannot run moves to
    /// another place only when that place is free and only on the person's press. Ready reads the plan's
    /// `elsewhere` offers, and "Run it free at <name>" sends exactly that offer (the model and the place's
    /// provider) to use-instead, setup's one code path; nothing is sent before the press.
    @Test("Run it free at a place posts the plan's offer to use-instead")
    func runItFreeAtAPlacePostsTheOffer() async throws {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        let plan = """
        {"runs":[],"skipped":[],"workflows":[],"offered":[],
         "refusals":["steps correct cannot run on this Mac: needs 24 GB. Or run it free at Studio Mac instead"],
         "elsewhere":[{"runtime":"mlx","model":"mlx-community/Qwen3-VL-8B","name":"Qwen3-VL 8B","steps":["correct"],
           "why":"needs 24 GB","said":"Or run it free at Studio Mac instead",
           "instead":[{"provider":"row-1","provider_name":"Studio Mac","provider_type":"ollama","place":"own_machine",
             "model":"mlx-community/Qwen3-VL-8B","name":"Qwen3-VL 8B","free":true}]}],
         "estimate":{"pages":2,"runs":[],"total_cost_usd":0}}
        """
        let store = makeStore { request in
            if request.url?.path == "/api/recipes/project/start/use-instead" {
                RecipesMockURLProtocol.calls += 1
                RecipesMockURLProtocol.bodies["/api/recipes/project/start/use-instead"] =
                    (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
                return Self.reply(request, 200, #"{"answers":null,"recipe":null}"#)
            }
            return Self.reply(request, 200, plan)
        }
        await store.loadStartPlan()
        let entry = try #require(store.elsewhere.first)
        let place = try #require(entry.instead?.first)
        #expect(place.free)
        #expect(RecipeElsewhereRows.buttonTitle(place) == "Run it free at Studio Mac")
        #expect(RecipesMockURLProtocol.calls == 0, "offered, never applied without the press")
        #expect(store.canStart == false)

        await store.useFreePlace(entry, place)

        let sent = RecipesMockURLProtocol.bodies["/api/recipes/project/start/use-instead"] ?? [:]
        #expect(RecipesMockURLProtocol.calls == 1)
        #expect(sent["model"] as? String == "mlx-community/Qwen3-VL-8B")
        #expect(sent["provider"] as? String == "row-1")
        #expect(sent["card"] == nil)
        #expect(store.errorMessage == nil)
    }
}

// MARK: Training offered later (#5660 item 9)

extension RecipeSetupStoreTests {
    /// A plan offering two steps: reading (a Kraken distillation here or on Hugging Face Jobs; spaCy not available)
    /// and finding regions (YOLO on this Mac). `teacher`: whether a reader has read the lines (the engine fills the
    /// distillation's params only then); `regionsReady`: whether enough regions are corrected.
    private static func trainPlanJSON(regionsReady: Bool, teacher: Bool = true) -> String {
        let regions = regionsReady
            ? #"{"ready":true,"pages":3,"min_pages":2,"more_pages":0,"sentence":null}"#
            : #"{"ready":false,"pages":1,"min_pages":2,"more_pages":1,"sentence":"Needs a person's regions on "#
                + #"at least 2 pages; this project has them on 1 page. Draw or correct the regions on 1 more page."}"#
        let taught = teacher ? #"{"scope_ids":["root-1"],"teacher":"kraken:kraken-zenodo-21788410"}"# : "null"
        return """
        {"runs":[],"skipped":[],"workflows":[],"offered":["train-a-model"],"refusals":[],
         "estimate":{"pages":9,"runs":[],"total_cost_usd":null},
         "train_offers":[
          {"step":"read-a-line","job":"read-a-line","title":"Train a model of your own for this step",
           "setting":{"mode":"offered","why":"asks first"},"does":"Trains once enough lines are corrected.",
           "readiness":{"ready":true,"lines":2400,"pages":3,"sentence":null},
           "ways":[
            {"method":"kraken","how":"distil","says":"Train a reader on the lines you have corrected",
             "available":true,
             "targets":[{"place":"this-mac","name":"this Mac","starts":"training.start_here","params":\(taught)},
                        {"place":"huggingface-jobs","name":"Hugging Face Jobs","starts":"training.start",
                         "params":\(taught)}]},
            {"method":"spacy-ner","how":"fine-tune","says":"Fine-tune a spaCy names model","available":false,"targets":[],
             "why":"not available yet: Fichero has no spaCy trainer"}]},
          {"step":"find-regions","job":"find-regions","title":"Train a model of your own for this step",
           "setting":{"mode":"offered","why":"asks first"},"does":"Trains once enough lines are corrected.",
           "readiness":\(regions),
           "ways":[{"method":"yolo","how":"fine-tune","says":"Train the region finder on the regions you corrected",
             "available":true,"targets":[{"place":"this-mac","name":"this Mac","starts":"training.start_regions_here",
             "params":{"name":"regions","scope_ids":["root-1","root-2"]}}]}]}]}
        """
    }

    /// WHY (#5660 item 9): a way that cannot run yet must say why in the engine's words (its need sentence, why it is
    /// not available, or that no reader has read the lines to learn from), never sit as a button that does nothing.
    @Test("each way says why it cannot train yet, in the engine's words; a ready way can")
    func trainOffersSayWhyNot() async throws {
        let waiting = makeStore { request in
            Self.reply(request, 200, Self.trainPlanJSON(regionsReady: false, teacher: false))
        }
        await waiting.loadStartPlan()
        let offers = waiting.trainOffers
        #expect(offers.map(\.step) == ["read-a-line", "find-regions"])
        let reading = try #require(offers.first), regions = try #require(offers.last)
        #expect(RecipeSetupStore.needSentence(reading) == nil, "enough corrected lines")
        #expect(RecipeSetupStore.trainDisabledReason(reading, reading.ways[0])
                == "No reader has read this project's lines yet.", "no teacher: the engine sent no params")
        #expect(RecipeSetupStore.trainDisabledReason(reading, reading.ways[1])
                == "not available yet: Fichero has no spaCy trainer")
        #expect(RecipeSetupStore.trainDisabledReason(regions, regions.ways[0])
                == RecipeSetupStore.needSentence(regions))
        #expect(RecipeSetupStore.needSentence(regions)?.hasPrefix("Needs a person's regions on at least 2 pages") == true)
        #expect(await waiting.startTraining(regions, way: regions.ways[0], at: regions.ways[0].targets[0]) == nil,
                "a way still waiting starts nothing")

        let ready = makeStore { request in Self.reply(request, 200, Self.trainPlanJSON(regionsReady: true)) }
        await ready.loadStartPlan()
        let readyRegions = try #require(ready.trainOffers.last), readyReading = try #require(ready.trainOffers.first)
        #expect(RecipeSetupStore.trainDisabledReason(readyRegions, readyRegions.ways[0]) == nil)
        #expect(RecipeSetupStore.trainDisabledReason(readyReading, readyReading.ways[0]) == nil, "a teacher: it can")
    }

    /// WHY (#5660 item 9): a ready button must post its place's action with the engine's params exactly, so the app
    /// never decides the scope or the teacher; and pages go to Hugging Face only after the person's yes, which alone
    /// adds `pages_may_leave`. Without the yes, nothing is posted.
    @Test("a ready way posts its action with the engine's params; Hugging Face only after the yes")
    func readyWayPostsItsAction() async throws {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        let store = makeStore { request in
            if request.url?.path == "/api/actions/invoke" {
                RecipesMockURLProtocol.calls += 1
                RecipesMockURLProtocol.bodies["\(RecipesMockURLProtocol.calls)"] =
                    (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
                return Self.reply(request, 200, #"{"ok":true,"result":{"job_id":"job-\#(RecipesMockURLProtocol.calls)"},"#
                                  + #""audit_id":"a1","changed_domains":["job"]}"#)
            }
            return Self.reply(request, 200, Self.trainPlanJSON(regionsReady: true))
        }
        func sent(_ call: Int) -> [String: Any] { RecipesMockURLProtocol.bodies["\(call)"] ?? [:] }
        func params(_ call: Int) -> [String: Any] { sent(call)["params"] as? [String: Any] ?? [:] }
        await store.loadStartPlan()
        let regions = try #require(store.trainOffers.last), reading = try #require(store.trainOffers.first)

        let yolo = regions.ways[0]
        #expect(await store.startTraining(regions, way: yolo, at: yolo.targets[0]) == "job-1")
        #expect(sent(1)["name"] as? String == "training.start_regions_here")
        #expect(params(1)["scope_ids"] as? [String] == ["root-1", "root-2"])
        #expect(params(1)["name"] as? String == "regions")
        #expect(params(1)["pages_may_leave"] == nil, "this Mac: nothing leaves, nothing asked")

        let kraken = reading.ways[0]
        #expect(await store.startTraining(reading, way: kraken, at: kraken.targets[0]) == "job-2")
        #expect(sent(2)["name"] as? String == "training.start_here")
        #expect(params(2)["teacher"] as? String == "kraken:kraken-zenodo-21788410")

        #expect(RecipeSetupStore.sendsPagesAway(kraken.targets[1]))
        #expect(await store.startTraining(reading, way: kraken, at: kraken.targets[1]) == nil, "no yes, nothing posted")
        #expect(RecipesMockURLProtocol.calls == 2)
        #expect(await store.startTraining(reading, way: kraken, at: kraken.targets[1], pagesMayLeave: true) == "job-3")
        #expect(sent(3)["name"] as? String == "training.start")
        #expect(params(3)["pages_may_leave"] as? Bool == true)
        #expect(params(3)["teacher"] as? String == "kraken:kraken-zenodo-21788410")
        #expect(store.errorMessage == nil)
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
        // Read until the stream ends (read returns 0), not while `hasBytesAvailable`: the client
        // writes the body into this stream from another thread, so under load the first check can
        // come before any bytes and read the body as empty; closing it then, while the writer is
        // still writing, crashed OpenAPIURLSession's HTTPBodyOutputStreamBridge (#5607).
        while true {
            let read = stream.read(&buffer, maxLength: buffer.count)
            guard read > 0 else { break }
            data.append(buffer, count: read)
        }
        return data
    }
}

extension RecipeSetupStoreTests {
    /// WHY (## 921): the plan is read from the SAVED project, so turning a step on must save (PUT) the answer before
    /// the plan is read again, or the step stays "not in the plan" and the button seems to do nothing.
    @Test("turning a step on sets the engine's answer, saves it, then reads the plan again")
    func turnOnSavesBeforeRereadingThePlan() async throws {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        var sequence: [String] = []
        var putBody: [String: Any] = [:]
        let store = makeStore { request in
            let path = request.url?.path ?? ""
            sequence.append("\(request.httpMethod ?? "") \(path)")
            if request.httpMethod == "PUT" {
                putBody = (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
                return Self.reply(request, 200, #"{"answers":{},"recipe":null}"#)
            }
            if path == "/api/recipes/project/start" {
                let inPlan = sequence.contains { $0.hasPrefix("PUT") }
                return Self.reply(request, 200, Self.planJSON(refusals: "").replacingOccurrences(
                    of: #""offered":"#,
                    with: #""step_choices":[{"step":"correct","job":"correct","name":"Correct","picked":null,"chosen_by":"setup","#
                        + #""in_plan":\#(inPlan),"candidates":[]}],"offered":"#))
            }
            return Self.reply(request, 200, Self.recipeJSON)
        }
        let menu = StepChoiceMenu(step: "correct", name: "Correct", chosenBy: .setup, inPlan: false,
                                  turnOnWords: "Have a second model check the reading, in Set Up",
                                  turnOnAnswer: "correct_with_a_second_model", turnOnValue: .yesNo(true), candidates: [])
        store.languages = ["es"]  // assemble needs the language and script answers, or it proposes nothing to save
        store.scripts = ["Latn"]
        await store.loadStartPlan()
        #expect(store.stepMenus.first?.inPlan == false)

        await store.turnOn(menu)

        let put = try #require(sequence.firstIndex { $0.hasPrefix("PUT") })
        let reread = try #require(sequence.lastIndex { $0 == "GET /api/recipes/project/start" })
        #expect(put < reread, "saved before the plan is read again: \(sequence)")
        let answers = putBody["answers"] as? [String: Any]
        #expect((answers?["job_answers"] as? [String: Any])?["correct_with_a_second_model"] as? Bool == true)
        #expect(store.stepMenus.first?.inPlan == true)
    }

    /// WHY (## 923, data loss): a refused assemble leaves recipe nil; saving then would PUT recipe: null over the saved
    /// recipe and the person's step choices. A 422 on /assemble sends no PUT and shows the engine's words.
    @Test("turning a step on when the engine refuses to assemble saves nothing and says why")
    func turnOnAfterARefusedAssembleSendsNoPut() async {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        var methods: [String] = []
        let store = makeStore { request in
            methods.append("\(request.httpMethod ?? "") \(request.url?.path ?? "")")
            return Self.reply(request, 422, #"{"detail":{"sentence":"This project has no material yet."}}"#)
        }
        store.languages = ["es"]
        store.scripts = ["Latn"]
        store.purposes = ["transcribe"]
        let menu = StepChoiceMenu(step: "correct", name: "Correct", chosenBy: .setup, inPlan: false,
                                  turnOnWords: "Have a second model check the reading, in Set Up",
                                  turnOnAnswer: "correct_with_a_second_model", turnOnValue: .yesNo(true), candidates: [])
        await store.turnOn(menu)
        #expect(!methods.contains { $0.hasPrefix("PUT") }, "no save after a refused assemble: \(methods)")
        #expect(store.errorMessage != nil)
    }

    @Test("a turn-on the app cannot read says so in words and sends nothing")
    func turnOnWithoutAReadableAnswerSaysSo() async {
        defer { RecipesMockURLProtocol.requestHandler = nil }
        var calls = 0
        let store = makeStore { request in calls += 1; return Self.reply(request, 200, "{}") }
        let menu = StepChoiceMenu(step: "correct", name: "Correct", chosenBy: .setup, inPlan: false,
                                  turnOnWords: "Turn on", candidates: [])
        await store.turnOn(menu)
        #expect(calls == 0)
        #expect(store.errorMessage?.contains("Turn it on in Set Up") == true)
    }
}

/// #6128 (`source.job.review-instructions-are-editable`): the person's edit to a review pass is kept with the project's
/// answers and a text equal to the default, or blank, is no edit.
struct ReviewInstructionsAnswersTests {
    @Test("an edited pass round-trips through the saved answers and an unedited one is left out")
    func roundTrips() throws {
        var answers = RecipeSetupAnswers.JobAnswers()
        answers.setReview("Only fix u/v.", for: "orthography", default: "the default")
        answers.setReview("the default", for: "abbreviations", default: "the default")
        #expect(answers.reviewInstructions == ["orthography": "Only fix u/v."])
        let back = try JSONDecoder().decode(RecipeSetupAnswers.JobAnswers.self, from: JSONEncoder().encode(answers))
        #expect(back.reviewInstructions == ["orthography": "Only fix u/v."])
        #expect(back.other["review_instructions"] == nil)
    }

    @Test("a blank is a reset: the box shows the default again")
    func blankResets() {
        var answers = RecipeSetupAnswers.JobAnswers()
        answers.setReview("mine", for: "orthography", default: "the default")
        #expect(answers.reviewText(for: "orthography", default: "the default") == "mine")
        answers.setReview("", for: "orthography", default: "the default")
        #expect(answers.reviewInstructions.isEmpty)
        #expect(answers.reviewText(for: "orthography", default: "the default") == "the default")
    }
}
