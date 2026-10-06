//
//  SetupFourStepsTests.swift
//  FicheroTests
//
//  Setup in four steps (`source/models-chains-and-projects.md` section 7b, ruled by the
//  maintainer 2026-10-06, #5492; `source.onboard.screens-in-order`): your project, your
//  material, what you want to do (a ticked purpose's questions open in place under it, an
//  unticked one shows nothing), Ready (the plan, what runs by itself, the optional rows Check on
//  your pages and Keep an export, Start). Written from the spec, not the code. Through the real
//  `RecipeSetupStore` over the generated client; only the transport is stubbed, on this suite's
//  own session.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class FourStepsURLProtocol: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) -> (Int, String))?
    /// Every request that reached the stub, in order: method, path and JSON body.
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
struct SetupFourStepsTests {

    private func makeStore(_ handler: @escaping (URLRequest) -> (Int, String)) -> RecipeSetupStore {
        FourStepsURLProtocol.handler = handler
        FourStepsURLProtocol.seen = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [FourStepsURLProtocol.self]
        return RecipeSetupStore(client: FicheroClient(baseURL: URL(string: "https://test.fichero")!,
                                                      libraryPath: "/tmp/four-steps.fichero",
                                                      session: URLSession(configuration: configuration)))
    }

    /// `GET /api/recipes/purposes`, in the engine's order: Transcribe (no questions), People,
    /// places and things (which kinds of names), Map places (names, then which gazetteer).
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

    private static let recipeJSON = """
    {"id":"generated","title":"t","purposes":["transcribe"],"steps":[
      {"id":"read","job":"read-a-line","title":"Read each line","reasons":[]},
      {"id":"train","job":"train-a-model","title":"Train a model","reasons":[]}],"gaps":[],"problems":[]}
    """

    private static let planJSON = """
    {"runs":[],"skipped":[],"workflows":[{"steps":["read-a-line"],"job":"read-a-line","workflow":"Transcribe",
      "workflow_id":"w1","runs_on":"this-mac"}],"offered":[],"refusals":[],
     "estimate":{"pages":12,"runs":[],"total_cost_usd":0}}
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

    // MARK: The steps

    /// WHY (#5492): setup was nine screens plus one per ticked job, too many; the maintainer ruled
    /// four. First run's setup after Welcome, Permissions and AI must be exactly those four, in
    /// that order, or a person is walked through screens the ruling took away.
    @Test("setup is four steps: your project, your material, what you want to do, Ready")
    func setupIsFourSteps() {
        let firstRun = FirstRunStep.steps(isCompanionPlatform: false)
        let setup = Array(firstRun.drop { [FirstRunStep.welcome, .permissions, .cloud].contains($0) })
        #expect(setup == [.project, .material, .purpose, .ready])
        #expect(setup.map(\.title) == ["Your Project", "Your Material", "What You Want to Do", "Ready"])
        #expect(FirstRunStep.newProjectSteps == setup, "Set Up New Project… runs the same four")
    }

    /// WHY (section 7b): Set Up… on an existing project starts at step 2, because the project
    /// already lives somewhere; asking where it lives again would offer to make a second project.
    @Test("Set Up… starts at step 2, Your material")
    func setUpStartsAtStepTwo() {
        #expect(FirstRunStep.setUpSteps == [.material, .purpose, .ready])
        #expect(!FirstRunStep.setUpSteps.contains(.project))
    }

    // MARK: Step 3, what you want to do

    /// WHY (#5492): ticking a purpose opens ITS questions in place under it, and nothing shows for
    /// an unticked one. People, places and things asks which kinds of names; Transcribe asks
    /// nothing; Map places, unticked, asks nothing. A question shown for a purpose not ticked would
    /// ask about work nobody asked for.
    @Test("ticking a purpose reveals only its questions")
    func tickingRevealsOnlyItsQuestions() async {
        let store = await purposeStore()
        #expect(store.purposeOptions.allSatisfy { store.questions(under: $0.id).isEmpty }, "nothing ticked asks nothing")

        store.toggle(purpose: "entities")
        #expect(store.questions(under: "entities") == ["find-names-tag-words"])
        #expect(store.questions(under: "map-places").isEmpty, "an unticked purpose shows nothing")
        #expect(store.questions(under: "transcribe").isEmpty)

        store.toggle(purpose: "transcribe")
        #expect(store.questions(under: "transcribe").isEmpty, "a purpose with no questions asks none")

        store.toggle(purpose: "map-places")
        #expect(store.questions(under: "map-places") == ["place-in-a-gazetteer"],
                "which kinds of names is asked once, under the purpose that first brings it")
    }

    /// WHY: Map places ticked alone brings names and the gazetteer, so it asks both; if it relied
    /// on another purpose to ask about names, nobody would be asked which kinds to find.
    @Test("a purpose ticked alone asks every question its jobs need")
    func purposeAloneAsksAll() async {
        let store = await purposeStore()
        store.toggle(purpose: "map-places")
        #expect(store.questions(under: "map-places") == ["find-names-tag-words", "place-in-a-gazetteer"])
    }

    /// WHY (#5492): unticking a purpose hides its questions and the plan drops its jobs: the
    /// engine is asked for a recipe without that purpose. A question left open, or a job left in
    /// the plan, would run work the person took back.
    @Test("unticking a purpose hides its questions and the recipe drops its jobs")
    func untickingHidesQuestionsAndDropsJobs() async throws {
        let store = await purposeStore()
        store.languages = ["es"]
        store.scripts = ["Latn"]
        store.toggle(purpose: "transcribe")
        store.toggle(purpose: "map-places")
        #expect(store.tickedJobs.contains("place-in-a-gazetteer"))

        store.toggle(purpose: "map-places")
        #expect(store.questions(under: "map-places").isEmpty)
        #expect(Set(store.tickedJobs) == ["find-lines", "read-a-line", "correct"], "only Transcribe's jobs stay")

        await store.assemble()
        let sent = try #require(FourStepsURLProtocol.seen.last { $0.path == "/api/recipes/assemble" })
        #expect(sent.body["purposes"] as? [String] == ["transcribe"], "the engine is asked without Map places")
    }

    // MARK: Step 4, Ready

    /// WHY (#5492): Ready shows the plan as one list, what runs by itself, then two optional rows,
    /// Check on your pages and Keep an export; anything optional can also be done later. If the
    /// optional rows were lost, the person could not compare readers or keep an export at setup;
    /// if they were required, setup could not finish without them.
    @Test("Ready shows the plan, what runs by itself and the two optional rows")
    func readyShowsTheOptionalRows() {
        let rows = RecipeReadyFields.Row.allCases
        #expect(rows == [.plan, .runsByItself, .checkOnYourPages, .keepAnExport])
        #expect(rows.filter(\.isOptional) == [.checkOnYourPages, .keepAnExport])
        #expect(rows.filter(\.isOptional).map(\.title) == ["Check on your pages", "Keep an export"])
    }

    /// WHY (#5492): what runs by itself is one choice. Choosing that new material runs, when the
    /// purposes proposed nothing, takes the plan's steps but never training
    /// (`source.recipe.train-never-automatic`); choosing Nothing runs automatically is saved so.
    @Test("what runs by itself is one choice, never training")
    func runsByItselfIsOneChoice() async throws {
        let store = await purposeStore()
        store.languages = ["es"]
        store.scripts = ["Latn"]
        await store.assemble()
        #expect(store.automaticAnswer.runs == false, "nothing ticked proposes nothing")

        store.setRunsByItself(true)
        #expect(store.automaticAnswer == .init(runs: true, steps: ["read-a-line"]))

        store.setRunsByItself(false)
        #expect(await store.save())
        let answers = try #require(FourStepsURLProtocol.seen.last { $0.method == "PUT" }?.body["answers"] as? [String: Any])
        #expect((answers["automatic"] as? [String: Any])?["runs"] as? Bool == false)
    }

    // MARK: Continue saves; Start saves first

    /// WHY (section 7b): Continue saves the answers so far into the project as a draft, so setup
    /// can be closed at any step; Start saves before it starts, so what starts is what is shown.
    /// If Start posted before the save, the engine would run the previous draft.
    @Test("Continue saves; Start saves, then starts")
    func continueSavesAndStartSavesFirst() async {
        let store = makeStore { request in
            request.url?.path == "/api/recipes/project/start" ? (200, Self.planJSON) : (200, #"{"answers":{},"recipe":null}"#)
        }
        #expect(FirstRunStep.material.savesDraft && FirstRunStep.purpose.savesDraft)
        #expect(await store.save())
        #expect(FourStepsURLProtocol.seen.map { "\($0.method) \($0.path)" } == ["PUT /api/recipes/project"])

        FourStepsURLProtocol.seen = []
        #expect(await RecipeReadyFields.start(store: store, keptExports: nil))
        #expect(FourStepsURLProtocol.seen.map { "\($0.method) \($0.path)" }
                == ["PUT /api/recipes/project", "POST /api/recipes/project/start"])
    }

    /// WHY: a refused save on Ready stops Start, with the engine's words on screen; starting after
    /// a refused save would run answers the engine never kept.
    @Test("a refused save stops Start")
    func refusedSaveStopsStart() async {
        let store = makeStore { _ in (500, #"{"detail":"The project is read-only."}"#) }
        #expect(await RecipeReadyFields.start(store: store, keptExports: nil) == false)
        #expect(!FourStepsURLProtocol.seen.contains { $0.path == "/api/recipes/project/start" })
        #expect(store.errorMessage != nil)
    }
}
