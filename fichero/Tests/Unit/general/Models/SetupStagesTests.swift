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
                    .stage("dates"), .ready])
    }

    @Test("source.recipe.leave-out-stage: Leave Out's toggle is the stage tick and the engine's `leave_out` answer, saved with the others")
    func leaveOutToggle() throws {
        let leaveOut = SetupStageChoice.Stage(id: "leave-out", jobs: ["leave-out"], needs: [])
        let store = RecipeSetupStore(client: StagesMockURLProtocol.client())
        store.stageChoice = SetupStageChoice(stages: [Self.lines, leaveOut], chosen: ["find-lines", "leave-out"])
        store.toggle(stage: "leave-out")
        #expect(store.jobAnswers[question: RecipeSetupStore.leaveOutQuestion] == .yesNo(false))
        #expect(store.removedJobs == ["leave-out"])
        store.toggle(stage: "leave-out")
        #expect(store.jobAnswers[question: RecipeSetupStore.leaveOutQuestion] == .yesNo(true))
        let saved = try JSONSerialization.jsonObject(with: JSONEncoder().encode(store.jobAnswers)) as? [String: Any]
        #expect(saved?["leave_out"] as? Bool == true, "an answer no typed field names is still saved, under the engine's key")
        let asked = try JSONDecoder().decode(Components.Schemas.StageQuestion.self, from: Data("""
        {"key": "leave_out", "ask": "Leave out what is not writing before reading?", "kind": "yes-no",
         "default": true, "answer": false, "read_by_a_step": false}
        """.utf8))
        #expect(SetupStagePage.answer(to: asked, in: RecipeSetupAnswers.JobAnswers()) == .yesNo(false), "the engine's answer shows")
    }

    @Test("source.recipe.second-reviewer: the mode picker reads the engine's question, in turn by default, and saves the choice under its key")
    func secondReviewMode() throws {
        let question = try JSONDecoder().decode(Components.Schemas.StageQuestion.self, from: Data("""
        {"key": "second_review_mode", "ask": "How should the second model review?", "kind": "one",
         "options": [{"id": "in-turn", "title": "In turn"}, {"id": "compare", "title": "Compare"},
                     {"id": "both", "title": "Both"}],
         "default": "in-turn", "answer": "in-turn", "read_by_a_step": true}
        """.utf8))
        var answers = RecipeSetupAnswers.JobAnswers()
        #expect(SetupStagePage.answer(to: question, in: answers) == .text("in-turn"), "in turn until the person chooses")
        answers[question: RecipeSetupStore.secondReviewModeQuestion] = .text("both")
        #expect(SetupStagePage.answer(to: question, in: answers) == .text("both"))
        let saved = try JSONSerialization.jsonObject(with: JSONEncoder().encode(answers)) as? [String: Any]
        #expect(saved?["second_review_mode"] as? String == "both", "an answer no typed field names is saved under the engine's key")
        #expect(RecipeSetupStore.secondReviewStepId == "correct-2")
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
        #expect(SetupStagePage.answer(to: kinds, in: answers) == .many([]), "every kind until the person names some (#5805)")
    }

    @Test("source.onboard.stages.kinds-are-open-ended: an open question has no options, every kind by default, and suggestions")
    func openEndedQuestion() throws {
        let statements = try JSONDecoder().decode(Components.Schemas.StageQuestion.self, from: Data("""
        {"key": "statement_kinds", "ask": "Which kinds of statements?", "kind": "many", "options": [],
         "default": [], "answer": [], "read_by_a_step": true, "open_ended": true, "suggestions": ["sale", "gift"]}
        """.utf8))
        #expect(statements.openEnded == true && (statements.options ?? []).isEmpty)
        #expect(SetupStagePage.answer(to: statements, in: RecipeSetupAnswers.JobAnswers()) == .many([]))
        #expect(statements.suggestions == ["sale", "gift"])
        // What the person types is kept as typed, saved under the question's key, and read back.
        var answers = RecipeSetupAnswers.JobAnswers()
        answers[question: "statement_kinds"] = .many(["Wills", "ship manifests"])
        #expect(SetupStagePage.answer(to: statements, in: answers) == .many(["Wills", "ship manifests"]))
        #expect(RecipeSetupAnswers.JobAnswers().entityKinds.isEmpty, "Names' kinds default to every kind")
    }

    @Test("a typed kind is added once, trimmed, whatever its case; suggestions already chosen are not offered again")
    func typedKindsAndChips() {
        #expect(StageKinds.adding("  Wills ", to: []) == ["Wills"])
        #expect(StageKinds.adding("wills", to: ["Wills"]) == ["Wills"], "not again under another case")
        #expect(StageKinds.adding("   ", to: ["Wills"]) == ["Wills"], "an empty word adds nothing")
        #expect(StageKinds.unchosen(["sale", "gift", "will"], chosen: ["Gift"]) == ["sale", "will"])
        #expect(StageKinds.unchosen([], chosen: []).isEmpty, "nothing is suggested before a try")
    }

    @Test("a tick box adds or removes its kind in any case; the typed extras are the kinds no box names")
    func tickBoxesAndExtras() {
        let all = ["people", "places", "organisations"]
        #expect(StageKinds.toggled("places", on: false, in: all) == ["people", "organisations"])
        #expect(StageKinds.toggled("Places", on: false, in: all) == ["people", "organisations"], "whatever its case")
        #expect(StageKinds.toggled("places", on: true, in: ["people"]) == ["people", "places"])
        #expect(StageKinds.toggled("people", on: true, in: ["People"]) == ["People"], "ticking a held kind changes nothing")
        #expect(StageKinds.extras(["people", "Wills", "places"], options: all) == ["Wills"])
        #expect(StageKinds.shown([], options: all) == all, "an old project's [] shows every box ticked")
        #expect(StageKinds.shown(["none"], options: all).isEmpty, "none shows every box unticked")
        #expect(StageKinds.saved([], options: all) == ["none"], "unticking the last box saves none, never []")
        #expect(StageKinds.saved([], options: []) == [], "a question with no boxes keeps [] as every kind")
        #expect(StageKinds.extras([], options: all).isEmpty)
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
          {"id": "find-lines", "title": "Find Lines", "sentence": "Finds the lines.", "example": "",
           "example_credit": {"title": "", "short_credit": "", "licence": "", "source_url": "", "licence_url": ""},
           "jobs": ["find-lines"],
           "on": true, "jobs_in_recipe": ["find-lines"], "questions": [], "needs": [], "sampleable": true,
           "tried_by": "bake-off"},
          {"id": "names", "title": "Names", "sentence": "Finds names.", "example": "",
           "example_credit": {"title": "", "short_credit": "", "licence": "", "source_url": "", "licence_url": ""},
           "jobs": ["find-names-tag-words"],
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

    @Test("source.try.every-job: a stage that cannot be tried says so in the engine's words (notTried); one that can has none")
    func aStageThatCannotBeTriedSaysSo() async {
        StagesMockURLProtocol.replies = ["GET /api/recipes/stages": (200, """
        {"items": [
          {"id": "find-lines", "title": "Find Lines", "sentence": "Finds the lines.", "example": "",
           "example_credit": {"title": "", "short_credit": "", "licence": "", "source_url": "", "licence_url": ""},
           "jobs": ["find-lines"],
           "on": true, "jobs_in_recipe": ["find-lines"], "questions": [], "needs": [], "sampleable": true,
           "tried_by": "bake-off", "not_tried": null},
          {"id": "names", "title": "Names", "sentence": "Finds names.", "example": "",
           "example_credit": {"title": "", "short_credit": "", "licence": "", "source_url": "", "licence_url": ""},
           "jobs": ["find-names-tag-words"],
           "on": false, "jobs_in_recipe": [], "questions": [], "needs": [], "sampleable": false, "tried_by": "workflow",
           "not_tried": "This stage cannot be tried on sample pages yet; it runs when you press Start."}
        ], "count": 2}
        """)]
        let store = RecipeSetupStore(client: StagesMockURLProtocol.client())
        await store.loadStages()
        let byId = Dictionary(uniqueKeysWithValues: store.stages.map { ($0.id, $0) })
        #expect(byId["find-lines"]?.notTried == nil)
        #expect(byId["names"]?.notTried == "This stage cannot be tried on sample pages yet; it runs when you press Start.")
    }

    @Test("source.onboard.stages.normalise-and-translate: Translate's target is a language question, kept as its tag")
    func translateIntoAnyLanguage() throws {
        let into = try JSONDecoder().decode(Components.Schemas.StageQuestion.self, from: Data("""
        {"key": "translate_into", "ask": "Into which language?", "kind": "language", "default": "en",
         "answer": null, "read_by_a_step": true}
        """.utf8))
        #expect(into.kind == .language)
        var answers = RecipeSetupAnswers.JobAnswers()
        #expect(SetupStagePage.answer(to: into, in: answers) == .text("en"))
        answers[question: "translate_into"] = .text("es")
        #expect(SetupStagePage.answer(to: into, in: answers) == .text("es"))
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
        #expect(SetupStageTryResult.summary(of: page) == "12 lines, 2 regions; 1 statement")
        #expect(result.names?.map(\.name) == ["Juan de Mosquera"])
    }

    // MARK: A try that is refused, failed or not made yet (#5806)

    @Test("a refused try (422) shows the engine's sentence and stops the spinner")
    func aRefusedTryShowsTheSentence() async {
        StagesMockURLProtocol.replies = [
            "GET /api/recipes/samples": (200, TryJSON.oneSample),
            "POST /api/recipes/stages/prepare-images/try": (422, TryJSON.refused)
        ]
        let store = SetupStageTryStore(client: StagesMockURLProtocol.client(), stageId: "prepare-images")
        await store.load()
        await store.tryIt()
        #expect(store.refusal == "Prepare Images cannot run yet: step 3 (read): the reader is not a model Fichero can find here")
        #expect(!store.isTrying)
    }

    @Test("a failed try says why, and a comparison that ended stops the spinner")
    func aFailedTryAndAFinishedComparison() throws {
        let failed = try JSONDecoder().decode(SetupStageTryResult.self, from: Data(TryJSON.failedNoReason.utf8))
        #expect(!failed.isUnderWay)
        #expect(failed.failure == "No line finder can be compared on this Mac yet.")
        let ended = try JSONDecoder().decode(SetupStageTryResult.self, from: Data(TryJSON.comparisonDone.utf8))
        #expect(ended.state == "waiting" && !ended.isUnderWay, "the comparison's state is what is running")
        let running = try JSONDecoder().decode(SetupStageTryResult.self, from: Data(TryJSON.comparisonRunning.utf8))
        #expect(running.isUnderWay)
    }

    @Test("a 404 on the stage's result is not tried yet, not still running")
    func aMissingResultIsNotTriedYet() async {
        StagesMockURLProtocol.replies = ["GET /api/recipes/samples": (200, TryJSON.oneSample)]
        let store = SetupStageTryStore(client: StagesMockURLProtocol.client(), stageId: "find-lines")
        await store.load()
        #expect(store.result == nil && !store.isTrying)
    }

    // MARK: About the material

    @Test("source.onboard.material.which-hand: the engine's hands for the script; Not sure stands alone; typed is kept")
    func whichHand() async {
        StagesMockURLProtocol.replies = ["GET /api/recipes/hands": (200, TryJSON.hands)]
        let store = RecipeSetupStore(client: StagesMockURLProtocol.client())
        store.scripts = ["Latn"]
        store.period = "16th century"
        await store.loadHands()
        #expect(store.handOptions.map(\.id) == ["secretary", "humanistic"])
        store.toggle(hand: "secretary")
        store.toggle(hand: "Procesal encadenada")
        #expect(store.hands == ["secretary", "Procesal encadenada"])
        store.toggle(hand: RecipeSetupStore.notSureHand)
        #expect(store.hands == ["not-sure"], "Not sure clears the others")
        store.toggle(hand: "humanistic")
        #expect(store.hands == ["humanistic"], "a hand ticked clears Not sure")
    }

    @Test("source.onboard.material.when-written: when, where and which hand are saved with the answers, as typed")
    func whenWhereHandRoundTrip() throws {
        let answers = RecipeSetupAnswers(period: "1650–1700", hands: ["secretary"], place: "Popayán")
        let data = try JSONEncoder().encode(answers)
        let object = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(object["period"] as? String == "1650–1700")
        #expect(object["hands"] as? [String] == ["secretary"])
        #expect(object["place"] as? String == "Popayán")
        #expect(try JSONDecoder().decode(RecipeSetupAnswers.self, from: data) == answers)
    }

    // MARK: Ready

    @Test("source.onboard.ready.words-not-engine-errors: a refusal names the step and says what to do, never the engine's form")
    func readyInWords() {
        let title = { (job: String) in job == "find-regions" ? "Find regions" : job }
        let raw = "step 1 (find-regions): the model ['yolo'] is not pinned in a known form for this step"
        let said = RecipeStartFields.words(for: raw, title: title)
        #expect(said == "Find regions: its model is not one Fichero can run yet. Choose a model for this step.")
        #expect(!said.contains("['yolo']") && !said.contains("step 1"))
        #expect(RecipeStartFields.words(for: "step 2 (read-a-line): no reader for Arabic yet", title: title)
                == "read-a-line: no reader for Arabic yet")
        #expect(RecipeStartFields.words(for: "Add a language first.", title: title) == "Add a language first.")
    }

    @Test("source.onboard.project.about-material: the pages are counted from what was added, as Start counts them")
    func pagesCounted() async {
        StagesMockURLProtocol.replies = ["GET /api/recipes/project/start": (200, """
        {"runs":[],"skipped":[],"workflows":[],"offered":[],"refusals":[],
         "estimate":{"pages":92,"runs":[],"total_cost_usd":0}}
        """)]
        let store = RecipeSetupStore(client: StagesMockURLProtocol.client())
        store.pages = 500  // a guess typed before anything was added
        #expect(store.countedPages == nil, "not read yet")
        await store.countPages()
        #expect(store.countedPages == 92)
        #expect(store.pages == 92, "the count replaces the guess")
    }

    @Test("source.onboard.stages.page-trains: a stage page offers training for its own steps only")
    func stagePageTrainsItsOwnSteps() async {
        StagesMockURLProtocol.replies = ["GET /api/recipes/project/start": (200, """
        {"runs":[],"skipped":[],"workflows":[],"offered":[],"refusals":[],
         "estimate":{"pages":92,"runs":[],"total_cost_usd":0},
         "train_offers":[
           {"step":"s2","job":"read-a-line","title":"Read each line","ways":[],
             "setting":{"mode":"offered","why":"asks first"},"does":"Trains once enough lines are corrected.",
             "readiness":{"ready":false}},
           {"step":"s5","job":"find-names-tag-words","title":"Find names","ways":[],
             "setting":{"mode":"offered","why":"asks first"},"does":"Trains once enough lines are corrected.",
             "readiness":{"ready":false}}]}
        """)]
        let store = RecipeSetupStore(client: StagesMockURLProtocol.client())
        await store.loadStartPlan()
        #expect(store.trainOffers.map(\.job) == ["read-a-line", "find-names-tag-words"], "the plan's offers, in order")
    }

    // MARK: What Fichero runs

    @Test("source.onboard.places-cap-projects: the screen's places are the engine's ids, this Mac the default")
    func whatFicheroRuns() {
        #expect(WhereTheWorkRuns.allCases.map(\.rawValue) == ["this-mac", "another-mac", "cloud", "acenet", "huggingface"])
        #expect(WhereTheWorkRuns.default == .thisMac)
    }
}

/// The engine's answers for a stage tried on the samples (`recipes/samples.py`).
private enum TryJSON {
    static let refused = """
    {"detail": "Prepare Images cannot run yet: step 3 (read): the reader is not a model Fichero can find here"}
    """
    static let failedNoReason = """
    {"stage": "find-lines", "state": "failed", "comparison": {"state": "failed",
     "reason": "No line finder can be compared on this Mac yet."}}
    """
    static let comparisonDone = """
    {"stage": "find-lines", "state": "waiting", "bakeoff": "b1", "comparison": {"state": "done", "reason": null}}
    """
    static let comparisonRunning = """
    {"stage": "find-lines", "state": "waiting", "bakeoff": "b1", "comparison": {"state": "running", "reason": null}}
    """
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
    static let hands = """
    {"items": [
      {"id": "secretary", "title": "Secretary", "script": "Latn", "centuries": "16th–17th century",
       "tags": ["secretary"], "looks": "angular, with a looped e"},
      {"id": "humanistic", "title": "Humanistic", "script": "Latn", "centuries": "15th–16th century",
       "tags": ["humanistic"], "looks": "round and upright"}
    ], "period_years": [1501, 1600], "not_sure": "not-sure"}
    """
    static let done = """
    {"stage": "names", "pages": ["p1"], "state": "done", "how": "its own steps on a copy of these pages",
     "per_page": [{"id": "p1",
                   "readings": [{"kind": "text", "level": "expanded", "text": "Juan de Mosquera, vecino de Popayán"}],
                   "segments": {"line": 12, "region": 2}, "statements": ["Juan sold a house"]}],
     "names": [{"name": "Juan de Mosquera", "type": "person"}]}
    """
}
