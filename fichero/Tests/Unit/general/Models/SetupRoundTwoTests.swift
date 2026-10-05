//
//  SetupRoundTwoTests.swift
//  FicheroTests
//
//  Setup, round 2 (`source/models-chains-and-projects.md` section 7b, ruled 2026-10-05;
//  #5478 #5479 #5481): purposes and jobs as checkboxes, each ticked job its own screen; a typed
//  language becomes its tag; a step's problem said once with its fix, never a model id; no
//  disclosure in setup. Through the real `RecipeSetupStore` over the generated client, with the
//  engine's responses as it answers them (recorded from `fichero-server/tests/unit/api/
//  test_setup_round_two.py`'s shapes); only the transport is stubbed, on this suite's session.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class RoundTwoURLProtocol: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) -> (Int, String))?
    nonisolated(unsafe) static var bodies: [String: [String: Any]] = [:]

    override static func canInit(with request: URLRequest) -> Bool {
        let path = request.url?.path ?? ""
        return path.hasPrefix("/api/recipes") || path.hasPrefix("/api/topics")
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let body = (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
        Self.bodies["\(request.httpMethod ?? "GET") \(request.url?.path ?? "")"] = body
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
struct SetupRoundTwoTests {

    private func makeStore(_ handler: @escaping (URLRequest) -> (Int, String)) -> RecipeSetupStore {
        RoundTwoURLProtocol.handler = handler
        RoundTwoURLProtocol.bodies = [:]
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [RoundTwoURLProtocol.self]
        return RecipeSetupStore(client: FicheroClient(baseURL: URL(string: "https://test.fichero")!,
                                                      libraryPath: "/tmp/round-two.fichero",
                                                      session: URLSession(configuration: configuration)))
    }

    private static func job(_ id: String) -> String {
        #"{"id":"\#(id)","name":"\#(id)","description":"what \#(id) does","topic":"\#(id)","layer":"l","#
            + #""takes":[],"gives":[],"compare":"","settings":[],"since":"1"}"#
    }

    /// The registry in its step order, as `GET /api/recipes/jobs` gives it.
    private static let jobsJSON = #"{"count":5,"items":["#
        + ["find-lines", "read-a-line", "correct", "find-names-tag-words", "place-in-a-gazetteer"]
            .map(job).joined(separator: ",") + "]}"

    /// `GET /api/recipes/purposes`: each purpose with its jobs (`source.onboard.purposes-show-their-jobs`).
    private static let purposesJSON = """
    {"count":3,"items":[
     {"id":"transcribe","title":"Transcribe","description":"Lines and readings.","runs_by_itself":true,
      "jobs":[{"id":"find-lines","title":"Find lines"},{"id":"read-a-line","title":"Read each line"},
              {"id":"correct","title":"Correct"}]},
     {"id":"entities","title":"People, places and things","description":"Names.","runs_by_itself":true,
      "jobs":[{"id":"find-lines","title":"Find lines"},{"id":"read-a-line","title":"Read each line"},
              {"id":"correct","title":"Correct"},{"id":"find-names-tag-words","title":"Find names"}]},
     {"id":"map-places","title":"Map places","description":"Places.","runs_by_itself":true,
      "jobs":[{"id":"find-lines","title":"Find lines"},{"id":"read-a-line","title":"Read each line"},
              {"id":"correct","title":"Correct"},{"id":"find-names-tag-words","title":"Find names"},
              {"id":"place-in-a-gazetteer","title":"Place in a gazetteer"}]}]}
    """

    private func registryStore() async -> RecipeSetupStore {
        let store = makeStore { request in
            switch request.url?.path {
            case "/api/recipes/purposes": (200, Self.purposesJSON)
            case "/api/recipes/jobs": (200, Self.jobsJSON)
            case "/api/topics": (200, #"{"count":0,"items":[]}"#)
            default: (404, "{}")
            }
        }
        await store.loadPurposes()
        await store.loadJobs()
        return store
    }

    private static func jobPages(_ store: RecipeSetupStore) -> [String] {
        SetupPage.pages(steps: FirstRunStep.setUpSteps, tickedJobs: store.tickedJobs).compactMap {
            if case .job(let job) = $0 { job } else { nil }
        }
    }

    // MARK: source.onboard.purpose-first, source.onboard.job-detail-screens (#5478)

    /// WHY (ruled 2026-10-05): purposes are checkboxes, any combination, and every ticked job
    /// adds its own screen. Ticking Transcribe and Map places must tick the union of their jobs,
    /// each once, in the registry's order, and add one screen per job between What it is and
    /// How it will be done. If the union doubled a job or lost one, setup would ask twice or
    /// never explain a job the recipe runs.
    @Test("two purposes tick their jobs, each once, and add their screens in step order")
    func twoPurposesTickTheirJobsAndAddScreens() async {
        let store = await registryStore()
        store.purposes = ["transcribe"]
        store.toggle(purpose: "map-places")

        let expected = ["find-lines", "read-a-line", "correct", "find-names-tag-words", "place-in-a-gazetteer"]
        #expect(store.tickedJobs == expected)
        #expect(Self.jobPages(store) == expected)
        let pages = SetupPage.pages(steps: FirstRunStep.setUpSteps, tickedJobs: store.tickedJobs)
        #expect(pages.firstIndex(of: .step(.about))! < pages.firstIndex(of: .job("find-lines"))!)
        #expect(pages.lastIndex(of: .job("place-in-a-gazetteer"))! < pages.firstIndex(of: .step(.recipe))!)
        #expect(store.purposeTitles(bringing: "find-names-tag-words") == ["Map places"],
                "a job a purpose brings says which purpose, and stays ticked while it is")
    }

    /// WHY: an unticked job adds no screen (ruled 2026-10-05). Unticking the purpose that
    /// brought a job must take that job's screen away, and keep the screens of jobs another
    /// ticked purpose still brings. A screen left behind would ask about work nobody asked for.
    @Test("unticking a purpose removes the screens only it brought")
    func untickingRemovesAScreen() async {
        let store = await registryStore()
        store.purposes = ["transcribe", "map-places"]
        #expect(Self.jobPages(store).contains("place-in-a-gazetteer"))

        store.toggle(purpose: "map-places")

        #expect(!Self.jobPages(store).contains("place-in-a-gazetteer"))
        #expect(!Self.jobPages(store).contains("find-names-tag-words"))
        #expect(Self.jobPages(store) == ["find-lines", "read-a-line", "correct"], "Transcribe's own screens stay")

        store.toggle(purpose: "transcribe")
        #expect(Self.jobPages(store).isEmpty, "none ticked is Not sure yet: no job screens")
    }

    /// WHY: a job ticked on its own (not by a purpose) adds its screen and reaches the engine as
    /// `jobs`, and the purposes go as a list; the saved answers carry no single `purpose`, so the
    /// engine never reads a stale one over the list.
    @Test("a job ticked on its own adds its screen and is sent with the purposes as lists")
    func jobTickedOnItsOwn() async throws {
        let store = await registryStore()
        store.purposes = ["transcribe"]
        store.toggle(job: "find-names-tag-words")
        #expect(Self.jobPages(store) == ["find-lines", "read-a-line", "correct", "find-names-tag-words"])

        RoundTwoURLProtocol.handler = { _ in (200, #"{"answers":{},"recipe":null}"#) }
        #expect(await store.save())
        let answers = try #require(RoundTwoURLProtocol.bodies["PUT /api/recipes/project"]?["answers"] as? [String: Any])
        #expect(answers["purposes"] as? [String] == ["transcribe"])
        #expect(answers["jobs"] as? [String] == ["find-names-tag-words"])
        #expect(answers["purpose"] == nil && answers["material"] == nil)
        #expect(answers["materials"] as? [String] == ["handwriting"])
    }

    // MARK: source.onboard.language-stored-as-tag (#5479)

    /// WHY (#5479): "spanish" reached the rules as typed and every reader was refused, because
    /// cards list tags. Return on a typed word must take the engine's answer and keep its TAG as
    /// the token (named Spanish), and the save must send `es`. A word the engine does not know
    /// is refused in words and never kept.
    @Test("a typed 'spanish' becomes the es token, and an unknown word is refused in words")
    func typedSpanishBecomesTheEsToken() async throws {
        let store = makeStore { request in
            let query = request.url?.query ?? ""
            if request.url?.path == "/api/recipes/languages", query.contains("q=spanish") {
                return (200, """
                {"count":2,"items":[
                 {"code":"ssp","name":"Spanish Sign Language","glottocode":"span1263","level":"language"},
                 {"code":"es","name":"Spanish","glottocode":"stan1288","level":"language"}]}
                """)
            }
            if request.url?.path == "/api/recipes/languages" { return (200, #"{"count":0,"items":[]}"#) }
            return (200, #"{"answers":{},"recipe":null}"#)
        }

        #expect(await store.addTyped("spanish", toScripts: false))
        #expect(store.languages == ["es"], "the exact name wins over a longer one the engine listed first")
        #expect(store.name(of: "es") == "Spanish")

        #expect(!(await store.addTyped("zzqx", toScripts: false)))
        #expect(store.languages == ["es"], "an unknown word is never kept as a language")
        #expect(store.errorMessage == "Fichero doesn't know a language called “zzqx”.")

        #expect(await store.save())
        let answers = try #require(RoundTwoURLProtocol.bodies["PUT /api/recipes/project"]?["answers"] as? [String: Any])
        #expect(answers["languages"] as? [String] == ["es"])
    }

    // MARK: source.onboard.widget-and-search: type-to-find only (#5479, ruled 2026-10-05)

    /// WHY (ruled 2026-10-05: languages and scripts are type-to-find only, no Browse… and no
    /// alphabetical list): typing shows the registry's matches in a dropdown under the field, and
    /// picking one makes a token that SHOWS the name and SAVES the tag. Spanish and Spanish Sign
    /// Language arrive together, and a language and its dialect can share a name, so a pick must
    /// become exactly the match picked; several picks make several tokens; × takes one away; and
    /// the save sends tags only. If a pick kept the typed text or the wrong match, the rules would
    /// refuse every reader again (#5479).
    @Test("a language picked from the dropdown becomes its token by tag; several; × removes one")
    func aPickFromTheDropdownBecomesATokenByTag() async throws {
        let store = makeStore { request in
            let query = request.url?.query ?? ""
            if request.url?.path == "/api/recipes/languages", query.contains("q=span") {
                return (200, """
                {"count":2,"items":[
                 {"code":"es","name":"Spanish","glottocode":"stan1288","level":"language"},
                 {"code":"ssp","name":"Spanish Sign Language","glottocode":"span1263","level":"language"}]}
                """)
            }
            if request.url?.path == "/api/recipes/languages", query.contains("q=lat") {
                return (200, #"{"count":1,"items":[{"code":"la","name":"Latin","glottocode":"lati1261","level":"language"}]}"#)
            }
            return (200, #"{"answers":{},"recipe":null}"#)
        }

        let spanMatches = await store.searchLanguages("span")
        #expect(spanMatches.map(\.code) == ["es", "ssp"], "typing asks the engine's registry, which answers by tag")
        #expect(!store.pick("span", among: spanMatches, toScripts: false), "a word still being typed is not a pick")
        #expect(store.languages.isEmpty)

        let spanish = try #require(spanMatches.first)
        #expect(store.pick(RecipeSetupStore.completion(for: spanish), among: spanMatches, toScripts: false))
        let latin = try #require(await store.searchLanguages("lat").first)
        #expect(store.pick(RecipeSetupStore.completion(for: latin), among: [latin], toScripts: false))

        #expect(store.languages == ["es", "la"], "several tokens, each by its tag, in the order picked")
        #expect(store.name(of: "es") == "Spanish" && store.name(of: "la") == "Latin", "each token shows its name")

        store.remove("es", fromScripts: false)
        #expect(store.languages == ["la"], "× removes that token and only it")

        #expect(await store.save())
        let answers = try #require(RoundTwoURLProtocol.bodies["PUT /api/recipes/project"]?["answers"] as? [String: Any])
        #expect(answers["languages"] as? [String] == ["la"], "the save sends tags, never names")
    }

    /// WHY: scripts are found the same way (ISO 15924), and what is kept is the CODE (`Latn`),
    /// shown by its name. Two scripts can share a word in their names ("Latin" and "Latin
    /// (Fraktur variant)"), so the pick must be the match picked, not the first one listed.
    @Test("a script picked from the dropdown is saved by its code, the one picked")
    func aScriptPickIsSavedByItsCode() async throws {
        let store = makeStore { request in
            if request.url?.path == "/api/recipes/scripts" {
                return (200, #"{"count":2,"items":[{"code":"Latn","name":"Latin"},{"code":"Latf","name":"Latin (Fraktur variant)"}]}"#)
            }
            return (200, #"{"answers":{},"recipe":null}"#)
        }
        let matches = await store.searchScripts("latin")
        let fraktur = try #require(matches.last)
        #expect(store.pick(RecipeSetupStore.completion(for: fraktur), among: matches, toScripts: true))
        #expect(store.scripts == ["Latf"])
        #expect(store.name(of: "Latf") == "Latin (Fraktur variant)")
        #expect(store.languages.isEmpty, "a script pick never lands among the languages")
    }

    // MARK: source.onboard.says-no-model, source.onboard.never-raw-model-ids (#5481)

    /// The assembled recipe as the engine gives it: a correcting step with no model, its one
    /// problem in words, and the rules' reason (model ids and all) in `detail` and `gap`.
    private static let recipeWithProblemJSON = """
    {"id":"generated","title":"t","purposes":["transcribe"],"steps":[
      {"id":"read","job":"read-a-line","title":"Read each line","sentence":"A model reads each line.",
       "card":{"id":"kraken:zenodo/10.5281/zenodo.13788177@unpinned","note":"McCATMuS"},
       "runs_on":"this-mac","uses_cloud":false,"reasons":[]},
      {"id":"correct","job":"correct","title":"Correct","sentence":"A language model corrects the reading.",
       "gap":"no local corrector knows es (mlx:Qwen/Qwen2.5-3B@main)","reasons":[],
       "problem":{"kind":"no-model-for-language","sentence":"No correcting model here knows Spanish yet.",
                  "fix":"download","fixes":["download","choose-cloud"],
                  "detail":"mlx:Qwen/Qwen2.5-3B@main: languages [en] lack es"}}],
     "gaps":["correct: no local corrector knows es (mlx:Qwen/Qwen2.5-3B@main)"],"problems":[]}
    """

    /// WHY (#5481): the maintainer saw a step's raw reason, model ids and all, twice. In setup a
    /// step's problem is said ONCE, in the engine's sentence, with its fix as a button; the
    /// reason as the rules wrote it, and any model id, never appears; a step that runs names its
    /// model by the card's name. The Inspector, not setup, shows the reason.
    @Test("a step problem shows its sentence once with its fix button and no model id")
    func stepProblemShownOnceWithItsFix() async throws {
        let store = makeStore { request in
            request.url?.path == "/api/recipes/assemble" ? (200, Self.recipeWithProblemJSON) : (200, #"{"count":0,"items":[]}"#)
        }
        store.languages = ["es"]
        store.scripts = ["Latn"]
        await store.assemble()
        let recipe = try #require(store.recipe)

        let setupLines = recipe.steps.flatMap { RecipeStepsView.lines(for: $0, store: store, inSetup: true) }
        let problems = setupLines.filter { if case .problem = $0 { true } else { false } }
        #expect(problems == [.problem("No correcting model here knows Spanish yet.")], "said once")
        #expect(setupLines.contains(.fix(title: "Download a model…", fix: "download")))
        #expect(setupLines.contains(.place("On this Mac · McCATMuS", cloud: false)))
        let said = setupLines.map { "\($0)" }.joined(separator: "\n")
        for raw in ["mlx:", "kraken:", "zenodo", "Qwen", "@", "no local corrector"] {
            #expect(!said.contains(raw), "setup shows no model id or raw reason (\(raw))")
        }

        let inspectorLines = recipe.steps.flatMap { RecipeStepsView.lines(for: $0, store: store, inSetup: false) }
        #expect(inspectorLines.contains(.detail("mlx:Qwen/Qwen2.5-3B@main: languages [en] lack es")),
                "the reason as the rules wrote it goes to the Inspector")
    }

    /// WHY (#5481): the `allow-cloud` fix answers the cloud question and proposes the recipe again
    /// with it; it must reach the engine as `cloud_allowed: true`, never silently stay local.
    @Test("the allow-cloud fix re-proposes the recipe with pages allowed to leave")
    func allowCloudFix() async {
        let store = makeStore { _ in (200, Self.recipeWithProblemJSON) }
        store.languages = ["es"]
        store.scripts = ["Latn"]
        await store.allowCloud()
        #expect(RoundTwoURLProtocol.bodies["POST /api/recipes/assemble"]?["cloud_allowed"] as? Bool == true)
    }

    // MARK: source.onboard.no-disclosure (#5481)

    /// WHY (#5481): setup has no More, Advanced or other disclosure; what a step needs to say is
    /// said once on the screen. A DisclosureGroup coming back into any setup view would hide a
    /// step's explanation or its problem behind a chevron again.
    @Test("no disclosure groups in setup")
    func noDisclosureInSetup() throws {
        let files = try AppSource.swiftFiles(under: "Views/Onboarding")
        #expect(files.count >= 5, "the setup views were found")
        for file in files {
            #expect(!file.code.contains("DisclosureGroup"), "\(file.path) has a disclosure")
        }
    }

    // MARK: source.onboard.what-runs-by-itself (#5478)

    /// WHY: What runs by itself proposes, before the person says, the steps of purposes that run
    /// by themselves, and is saved with the project as `answers.automatic`; Nothing runs
    /// automatically must be saved as such, so an import after Start runs nothing.
    @Test("what runs by itself is proposed from the purposes and saved as the person chose")
    func whatRunsByItself() async throws {
        let store = makeStore { request in
            switch request.url?.path {
            case "/api/recipes/purposes": (200, Self.purposesJSON)
            case "/api/recipes/assemble": (200, Self.recipeWithProblemJSON)
            default: (200, #"{"answers":{},"recipe":null}"#)
            }
        }
        await store.loadPurposes()
        store.languages = ["es"]
        store.scripts = ["Latn"]
        await store.assemble()
        #expect(store.automaticAnswer == .init(runs: true, steps: ["read-a-line", "correct"]))

        store.automatic = .init(runs: false, steps: store.automaticAnswer.steps)
        #expect(await store.save())
        let answers = try #require(RoundTwoURLProtocol.bodies["PUT /api/recipes/project"]?["answers"] as? [String: Any])
        let automatic = try #require(answers["automatic"] as? [String: Any])
        #expect(automatic["runs"] as? Bool == false)
    }
}
