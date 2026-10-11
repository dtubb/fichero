@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class StagesMockURLProtocol: URLProtocol {
    /// "METHOD /path" → (status, JSON); a request not listed answers 404.
    nonisolated(unsafe) static var replies: [String: (Int, String)] = [:]
    nonisolated(unsafe) static var seen: [String] = []
    override static func canInit(with request: URLRequest) -> Bool {
        (request.url?.path ?? "").hasPrefix("/api/recipes/")
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let key = "\(request.httpMethod ?? "GET") \(request.url?.path ?? "")"
        Self.seen.append(key)
        let (status, json) = Self.replies[key] ?? (404, #"{"detail": "not found"}"#)
        let response = HTTPURLResponse(
            url: request.url!, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}

    static func client() -> FicheroClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StagesMockURLProtocol.self]
        return FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/test.fichero",
                             session: URLSession(configuration: configuration))
    }
}

/// Choosing the stages, and each stage's questions (sections 7c and 7d, #5668). Pure over the engine's list, and
/// through the generated client for `GET /api/recipes/stages`.
@MainActor
@Suite(.serialized)
struct SetupStagesTests {
    private static let names = SetupStageChoice.Stage(id: "names", jobs: ["find-names-tag-words"], needs: [])
    private static let dates = SetupStageChoice.Stage(
        id: "dates", jobs: ["work-out-dates"], needs: [(stage: "names", why: "Dates & Times needs Names")]
    )
    private static let lines = SetupStageChoice.Stage(id: "find-lines", jobs: ["find-lines"], needs: [])
    private static let read = SetupStageChoice.Stage(
        id: "read", jobs: ["read-a-line"], needs: [(stage: "find-lines", why: "Read needs Find Lines")]
    )

    private func choice(_ chosen: Set<String> = []) -> SetupStageChoice {
        SetupStageChoice(stages: [Self.lines, Self.read, Self.names, Self.dates], chosen: chosen)
    }

    // MARK: Choose the Stages

    @Test("source.onboard.stages.needs-are-ticked: ticking a stage ticks what it needs, which cannot be unticked")
    func needsAreTicked() {
        var choice = choice()
        choice.toggle("dates")
        #expect(choice.chosen == ["dates", "names"])
        #expect(choice.neededBecause("names") == ["Dates & Times needs Names"])
        choice.toggle("names")
        #expect(choice.chosen.contains("names"), "a needed stage stays ticked")
        choice.toggle("dates")
        choice.toggle("names")
        #expect(choice.chosen.isEmpty, "once nothing needs it, it unticks")
    }

    @Test("source.onboard.project.steps: the stage pages come in the engine's order, whatever order they were ticked in")
    func pagesInEngineOrder() {
        var choice = choice()
        choice.toggle("dates")
        choice.toggle("read")
        #expect(choice.chosenInOrder == ["find-lines", "read", "names", "dates"])
        #expect(SetupStep.projectSteps(chosenStages: choice.chosenInOrder, isNewProject: false)
                == [.addMaterial, .aboutMaterial, .stages, .stage("find-lines"), .stage("read"), .stage("names"),
                    .stage("dates"), .train, .ready])
    }

    @Test("source.onboard.stages.goals-are-shortcuts: a goal ticks its stages; a stage unticked afterwards stays so")
    func goalsAreShortcuts() {
        var choice = choice()
        choice.applyGoal(jobs: ["read-a-line", "find-names-tag-words"])
        #expect(choice.chosen == ["read", "find-lines", "names"])
        choice.toggle("names")
        #expect(!choice.chosen.contains("names"))
    }

    @Test("the choice becomes the answers: chosen stages' jobs added, every other stage's taken out")
    func choiceBecomesJobs() {
        let choice = choice(["find-lines", "read"])
        #expect(choice.jobsAddedAndRemoved.added == ["find-lines", "read-a-line"])
        #expect(choice.jobsAddedAndRemoved.removed == ["find-names-tag-words", "work-out-dates"])
    }

    // MARK: A stage's questions

    @Test("source.onboard.stages.page-asks-its-questions: an answer shows the person's, else the engine's, else the default")
    func questionAnswers() throws {
        var answers = RecipeSetupAnswers.JobAnswers()
        // As the engine sends it (`StageQuestion`), default and all.
        let calendars = try JSONDecoder().decode(Components.Schemas.StageQuestion.self, from: Data("""
        {"key": "calendars", "ask": "Which calendars?", "kind": "many",
         "options": [{"id": "gregorian", "title": "Gregorian"}, {"id": "julian", "title": "Julian"}],
         "default": ["gregorian"], "answer": null, "read_by_a_step": false}
        """.utf8))
        #expect(SetupStagePage.answer(to: calendars, in: answers) == .many(["gregorian"]), "the default")
        answers[question: "calendars"] = .many(["julian"])
        #expect(SetupStagePage.answer(to: calendars, in: answers) == .many(["julian"]), "the person's")
        // A typed field answers for its own key.
        let kinds = Components.Schemas.StageQuestion(key: "entity_kinds", ask: "Which kinds of names?", kind: .many,
                                                     readByAStep: true)
        #expect(SetupStagePage.answer(to: kinds, in: answers) == .many(["people", "places"]))
    }

    @Test("a stage question's answer is saved under its key in job_answers, beside the typed ones, and read back")
    func otherAnswersRoundTrip() throws {
        var answers = RecipeSetupAnswers.JobAnswers()
        answers[question: "calendars"] = .many(["julian"])
        answers[question: "two_pages_per_image"] = .yesNo(true)
        answers[question: "gazetteer"] = .text("wikidata")
        let data = try JSONEncoder().encode(answers)
        let object = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(object["calendars"] as? [String] == ["julian"])
        #expect(object["two_pages_per_image"] as? Bool == true)
        #expect(object["gazetteer"] as? String == "wikidata")
        let back = try JSONDecoder().decode(RecipeSetupAnswers.JobAnswers.self, from: data)
        #expect(back == answers)
    }

    // MARK: From the engine

    @Test("source.onboard.stages.stages-list-from-the-engine: the stages and what is on come from GET /api/recipes/stages")
    func stagesFromTheEngine() async {
        StagesMockURLProtocol.replies = ["GET /api/recipes/stages": (200, """
        {"items": [
          {"id": "find-lines", "title": "Find Lines", "sentence": "Finds the lines.", "example": "", "jobs": ["find-lines"],
           "on": true, "jobs_in_recipe": ["find-lines"], "questions": [], "needs": [], "sampleable": true,
           "tried_by": "bake-off"},
          {"id": "names", "title": "Names", "sentence": "Finds names.", "example": "", "jobs": ["find-names-tag-words"],
           "on": false, "jobs_in_recipe": [], "questions": [], "needs": [], "sampleable": true, "tried_by": "workflow"}
        ], "count": 2}
        """)]
        let store = RecipeSetupStore(client: StagesMockURLProtocol.client())
        await store.loadStages()
        #expect(store.stages.map(\.id) == ["find-lines", "names"])
        #expect(store.chosenStageIds == ["find-lines"], "what the engine has on")
        #expect(store.stageTitles["names"] == "Names")
        store.toggle(stage: "names")
        #expect(store.chosenStageIds == ["find-lines", "names"])
        #expect(store.addedJobs == ["find-lines", "find-names-tag-words"])
        #expect(store.removedJobs.isEmpty)
    }

    // MARK: On your pages

    @Test("source.onboard.stages.samples-proposed: the samples, with why; a cloud try asks its cost before it runs")
    func samplesAndTheCostQuestion() async {
        StagesMockURLProtocol.seen = []
        StagesMockURLProtocol.replies = [
            "GET /api/recipes/samples": (200, TryJSON.twoSamples),
            "POST /api/recipes/stages/names/try": (402, TryJSON.costFirst)
        ]
        let store = SetupStageTryStore(client: StagesMockURLProtocol.client(), stageId: "names")
        await store.load()
        #expect(store.samples.map(\.why) == ["your first page", "the largest image"])
        #expect(store.result == nil, "not tried yet")
        await store.tryIt()
        #expect(store.costQuestion?.contains("about $0.04") == true, "the cost, in the engine's words")
        #expect(store.result == nil, "nothing ran without the yes")
    }

    @Test("source.onboard.stages.sample-result: a finished try reads per page, with the names found")
    func aTryReadsPerPage() async throws {
        StagesMockURLProtocol.replies = [
            "GET /api/recipes/samples": (200, TryJSON.oneSample),
            "POST /api/recipes/stages/names/try": (200, TryJSON.done)
        ]
        let store = SetupStageTryStore(client: StagesMockURLProtocol.client(), stageId: "names")
        await store.load()
        await store.tryIt()
        let result = try #require(store.result)
        #expect(result.state == "done" && !result.isUnderWay)
        let page = try #require(result.perPage?.first)
        #expect(store.name(of: page.id) == "f. 1r")
        #expect(SetupStageTryResult.summary(of: page) == "12 line, 2 region; 1 statement")
        #expect(result.names?.map(\.name) == ["Juan de Mosquera"])
    }

    // MARK: What Fichero runs

    @Test("source.onboard.app.what-fichero-runs: what Fichero does and with what, and the two accounts it suggests")
    func whatFicheroRuns() {
        #expect(WhatFicheroRuns.rows.map(\.work)
                == ["Reading pages", "Finding regions and lines", "Names and statements", "Speech", "Remote models"])
        #expect(WhatFicheroRuns.rows.first?.with == "Kraken, Apple Vision, MLX vision models")
        #expect(WhatFicheroRuns.accounts.map(\.providerType) == ["huggingface", "openrouter"])
    }
}

/// The engine's answers for a stage tried on the samples (`recipes/samples.py`).
private enum TryJSON {
    static let twoSamples = """
    {"chosen_by": "fichero", "pages": [{"id": "p1", "name": "f. 1r", "why": "your first page"},
     {"id": "p9", "name": "f. 9v", "why": "the largest image"}]}
    """
    static let oneSample = """
    {"chosen_by": "fichero", "pages": [{"id": "p1", "name": "f. 1r", "why": "your first page"}]}
    """
    static let costFirst = """
    {"detail": "Trying Names on 2 pages uses the cloud and costs about $0.04: try it again with your yes to the cost"}
    """
    static let done = """
    {"stage": "names", "pages": ["p1"], "state": "done", "how": "its own steps on a copy of these pages",
     "per_page": [{"id": "p1",
                   "readings": [{"kind": "text", "level": "expanded", "text": "Juan de Mosquera, vecino de Popayán"}],
                   "segments": {"line": 12, "region": 2}, "statements": ["Juan sold a house"]}],
     "names": [{"name": "Juan de Mosquera", "type": "person"}]}
    """
}
