//
//  ModelFinderStoreTests.swift
//  FicheroTests
//
//  The model finder (#5611, `source.find.app-*`): the store reads the engine's candidates
//  through the generated client, follows the online search through Activity's job list (never a
//  poller of its own), downloads a candidate by the download the engine names for it, and Use for
//  This Step sends any candidate through setup's use-candidate (#5612). Driven through the generated client
//  against a stub scoped to this suite's own host, recording what each path was sent.
//

@testable import Fichero
import FicheroAPIClient
import XCTest

private nonisolated struct FinderRequest {
    let path: String
    let method: String
    let query: [String: String]
    let body: Data
}

private final class FinderMockURLProtocol: URLProtocol {
    private static let lock = NSLock()
    nonisolated(unsafe) static var handler: ((URLRequest) -> (Int, String))?
    /// How many candidate reads asked with online=true, so a handler can answer the first and the
    /// later ones differently without capturing state of its own.
    nonisolated(unsafe) static var onlineReads = 0
    nonisolated(unsafe) private static var log: [FinderRequest] = []

    static func reset(_ handler: @escaping (URLRequest) -> (Int, String)) {
        lock.lock()
        self.handler = handler
        log = []
        onlineReads = 0
        lock.unlock()
    }

    /// Every request that reached the stub for this path, in order.
    static func requests(to path: String) -> [FinderRequest] {
        lock.lock()
        defer { lock.unlock() }
        return log.filter { $0.path == path }
    }

    // swiftlint:disable:next static_over_final_class
    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.host == "finder.test"
    }

    // swiftlint:disable:next static_over_final_class
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url else { return }
        let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
        let query = Dictionary(items.map { ($0.name, $0.value ?? "") }, uniquingKeysWith: { _, last in last })
        let body = request.bodyOrStream()
        Self.lock.lock()
        Self.log.append(FinderRequest(path: url.path, method: request.httpMethod ?? "", query: query, body: body))
        if query["online"] == "true" { Self.onlineReads += 1 }
        let handler = Self.handler
        Self.lock.unlock()
        let (status, json) = handler?(request) ?? (404, "{}")
        guard let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1",
                                             headerFields: ["Content-Type": "application/json"]) else { return }
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

/// The candidates a stub answers with, as the engine sends them.
private nonisolated enum FinderJSON {
    static let shipped = """
    {"id":"kraken:catmus@1","name":"CATMuS Medieval","source":"shipped",
     "offered_because":"a card that ships with Fichero","pin":{"zenodo":"10.5281/zenodo.1"},
     "jobs":["read-a-line"],"open_licence":true,"size":"0.02 GB","size_gb":0.02,
     "measured":"unmeasured on your pages until a bake-off measures it","in_recipe_rules":true,"rule_rank":1,
     "runs_where":"this_mac","availability":"ships","availability_words":"Ships with Fichero"}
    """
    static let found = """
    {"id":"mlx:hf/example/ocr-mlx@main","name":"Example OCR","source":"hugging-face",
     "offered_because":"reads handwriting; lists Spanish","pin":{"hf":"example/ocr-mlx","revision":"main"},
     "jobs":["read-a-line"],"licence":"cc-by-nc-4.0","open_licence":false,"size":"size not stated",
     "measured":"unmeasured on your pages until a bake-off measures it","in_recipe_rules":true,"rule_rank":2,
     "installed":false,"runs_where":"this_mac","availability":"download","availability_words":"Download",
     "download":{"runtime":"mlx","model":"Example-OCR","action":"model.download",
                 "params":{"runtime":"mlx","model":"Example-OCR"}}}
    """

    static func list(_ items: [String], searchJob: String? = nil) -> String {
        let job = searchJob.map { ",\"search_job\":\($0)" } ?? ""
        return """
        {"job":"read-a-line","count":\(items.count),"items":[\(items.joined(separator: ","))],
         "sources":[{"source":"shipped","state":"read","count":1,"detail":"the cards that ship with Fichero"}]\(job)}
        """
    }

    static func isOnline(_ request: URLRequest) -> Bool {
        request.url?.query?.contains("online=true") == true
    }
}

@MainActor
final class ModelFinderStoreTests: XCTestCase {
    private static let candidatesPath = "/api/recipes/candidates"
    private static let query = ModelFinderStore.Query(scripts: ["Latn"], languages: ["es"], material: "handwriting")

    private func makeClient() -> FicheroClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [FinderMockURLProtocol.self]
        return FicheroClient(
            baseURL: URL(string: "https://finder.test")!,
            libraryPath: "/tmp/finder.fichero",
            session: URLSession(configuration: configuration)
        )
    }

    override func tearDown() {
        FinderMockURLProtocol.handler = nil
        super.tearDown()
    }

    private func candidateReads() -> [FinderRequest] {
        FinderMockURLProtocol.requests(to: Self.candidatesPath)
    }

    /// WHY (`source.find.app-finder-three-hosts`): the finder shows what the engine answered for the
    /// project's answers; if it dropped a script or language, or searched online unasked, the cards
    /// would answer a question nobody asked (and reach the network without a press).
    func testLoadAsksForTheQueryAndKeepsTheEnginesOrder() async throws {
        FinderMockURLProtocol.reset { _ in (200, FinderJSON.list([FinderJSON.shipped, FinderJSON.found])) }
        let store = ModelFinderStore(client: makeClient())

        await store.load(Self.query)

        let sent = try XCTUnwrap(candidateReads().last)
        XCTAssertEqual(sent.method, "GET")
        XCTAssertEqual(sent.query["scripts"], "Latn")
        XCTAssertEqual(sent.query["languages"], "es")
        XCTAssertEqual(sent.query["job"], "read-a-line")
        XCTAssertEqual(sent.query["material"], "handwriting")
        XCTAssertEqual(sent.query["online"], "false", "nothing is searched online before Search Online is pressed")
        XCTAssertEqual(store.candidates.map(\.id), ["kraken:catmus@1", "mlx:hf/example/ocr-mlx@main"])
        XCTAssertEqual(store.candidates.last?.size, "size not stated")
        XCTAssertEqual(store.sources.count, 1)
        XCTAssertFalse(store.isSearching)
        XCTAssertNil(store.errorMessage)
    }

    /// WHY (`source.find.app-searching-line`): the online search is an Activity job; the finder says
    /// "Searching online…" with what the job is doing, and reads the list again once Activity no
    /// longer lists the job (done), so what it found appears without a second press.
    func testOnlineSearchShowsTheSearchingLineAndRefreshesWhenTheJobEnds() async throws {
        FinderMockURLProtocol.reset { request in
            guard FinderJSON.isOnline(request) else { return (200, FinderJSON.list([FinderJSON.shipped])) }
            return FinderMockURLProtocol.onlineReads == 1
                ? (200, FinderJSON.list([FinderJSON.shipped], searchJob: #"{"id":"job-1","state":"running"}"#))
                : (200, FinderJSON.list([FinderJSON.shipped, FinderJSON.found],
                                        searchJob: #"{"id":"job-1","state":"done"}"#))
        }
        let store = ModelFinderStore(client: makeClient())
        await store.load(Self.query)

        await store.searchOnline()
        XCTAssertTrue(store.isSearching)
        XCTAssertEqual(store.searchLine, "Searching online…")
        XCTAssertEqual(candidateReads().last?.query["online"], "true")

        await store.observe([ActivityJob(id: "job-1", taskType: "find-models", name: "Find models",
                                         state: .running, reason: "asking Hugging Face")])
        XCTAssertEqual(store.searchLine, "Searching online… asking Hugging Face")
        XCTAssertEqual(candidateReads().count, 2, "a running job in Activity is not a reason to read the list again")

        await store.observe([])

        let reads = candidateReads()
        XCTAssertEqual(reads.count, 3, "the list is read once more when the job leaves Activity")
        XCTAssertEqual(reads.last?.query["online"], "true", "with online, so the finished job's findings come back")
        XCTAssertFalse(store.isSearching)
        XCTAssertNil(store.searchLine)
        XCTAssertEqual(store.candidates.map(\.id), ["kraken:catmus@1", "mlx:hf/example/ocr-mlx@main"])
    }

    /// WHY: a failed search says why in place of the line, and is never queued again by itself:
    /// re-reading with online after a failure would start another search the person did not ask for.
    func testFailedSearchSaysWhyAndReadsWithoutOnline() async throws {
        FinderMockURLProtocol.reset { request in
            guard FinderJSON.isOnline(request) else { return (200, FinderJSON.list([FinderJSON.shipped])) }
            return (200, FinderJSON.list([FinderJSON.shipped], searchJob: #"{"id":"job-2","state":"waiting"}"#))
        }
        let store = ModelFinderStore(client: makeClient())
        await store.load(Self.query)
        await store.searchOnline()
        XCTAssertTrue(store.isSearching)

        await store.observe([ActivityJob(id: "job-2", taskType: "find-models", name: "Find models",
                                         state: .failed, reason: "Hugging Face did not answer")])

        XCTAssertFalse(store.isSearching)
        XCTAssertEqual(store.searchFailure, "Hugging Face did not answer")
        XCTAssertEqual(candidateReads().last?.query["online"], "false")
        XCTAssertEqual(FinderMockURLProtocol.onlineReads, 1, "the failed search is not started again")
    }

    /// WHY (bounded fallback): a search that ended between two Activity polls is never listed; after
    /// a few snapshots without it the finder reads once more rather than saying Searching for ever.
    func testASearchNeverSeenInActivityEndsAfterTheBoundedSnapshots() async throws {
        FinderMockURLProtocol.reset { request in
            guard FinderJSON.isOnline(request) else { return (200, FinderJSON.list([FinderJSON.shipped])) }
            return FinderMockURLProtocol.onlineReads == 1
                ? (200, FinderJSON.list([FinderJSON.shipped], searchJob: #"{"id":"job-3","state":"running"}"#))
                : (200, FinderJSON.list([FinderJSON.shipped, FinderJSON.found],
                                        searchJob: #"{"id":"job-3","state":"done"}"#))
        }
        let store = ModelFinderStore(client: makeClient())
        await store.load(Self.query)
        await store.searchOnline()
        let other = [ActivityJob(id: "embed-1", taskType: "embed", name: "Embedding")]

        for _ in 1..<ModelFinderStore.unseenLimit { await store.observe(other) }
        XCTAssertTrue(store.isSearching, "a snapshot older than the job is not the job's end")
        XCTAssertEqual(FinderMockURLProtocol.onlineReads, 1)

        await store.observe(other)
        XCTAssertFalse(store.isSearching)
        XCTAssertEqual(store.candidates.count, 2)
    }

    /// WHY (`source.find.app-card-actions`, #5612): Download goes through the one download route by the
    /// runtime and model the engine names in the candidate's `download` (the Start plan's own action),
    /// never a repo the app reads out of the pin; a candidate with no `download` has nothing to press,
    /// and pressing it anyway sends nothing.
    func testDownloadPostsTheCandidatesOwnDownloadToTheDownloadRoute() async throws {
        FinderMockURLProtocol.reset { request in
            if request.url?.path.hasPrefix("/api/local-models/download") == true {
                return (200, #"{"status":"queued","model_type":"mlx","model_id":"Example-OCR","job_id":"dl-1"}"#)
            }
            return (200, FinderJSON.list([FinderJSON.shipped, FinderJSON.found]))
        }
        let store = ModelFinderStore(client: makeClient())
        await store.load(Self.query)
        let shipped = try XCTUnwrap(store.candidates.first)
        let found = try XCTUnwrap(store.candidates.last)
        XCTAssertNil(shipped.download)

        await store.download(shipped)
        await store.download(found)

        XCTAssertEqual(FinderMockURLProtocol.requests(to: "/api/local-models/download/mlx/Example-OCR").count, 1)
        XCTAssertEqual(FinderMockURLProtocol.requests(to: "/api/local-models/download/mlx/Example-OCR").first?.method,
                       "POST")
        XCTAssertEqual(FinderMockURLProtocol.requests(to: "/api/local-models/download/mlx/example/ocr-mlx").count, 0)
        // The one download path (#5620): the card's download is followed by the project's downloads.
        XCTAssertTrue(store.downloads.isActive(.init(runtime: "mlx", model: "Example-OCR")))
        XCTAssertNil(ModelFinderStore.downloadKey(shipped))
        XCTAssertNil(store.errorMessage)
    }

    /// WHY (`source.find.app-card-says`, #5612, #5660 item 3): the card says where it stands for this Mac in the
    /// engine's own words (`availability_words`: "Ships with Fichero", "Download"), with a licence that is not
    /// open; a shipped card does not repeat "a card that ships with Fichero"; a found one says why it was found.
    func testCardSaysWhetherItIsHereAndWhereItRuns() async throws {
        FinderMockURLProtocol.reset { _ in (200, FinderJSON.list([FinderJSON.shipped, FinderJSON.found])) }
        let store = ModelFinderStore(client: makeClient())
        await store.load(Self.query)
        let shipped = try XCTUnwrap(store.candidates.first)
        let found = try XCTUnwrap(store.candidates.last)
        XCTAssertEqual(ModelFinderCard.facts(found), "Download · licence: cc-by-nc-4.0")
        XCTAssertEqual(ModelFinderCard.facts(shipped), "Ships with Fichero")
        XCTAssertNil(ModelFinderCard.whyOffered(shipped), "a shipped card does not repeat that it ships")
        XCTAssertEqual(ModelFinderCard.whyOffered(found), found.offeredBecause)
        XCTAssertFalse(ModelFinderCard.isChosen(shipped))
    }

    /// WHY (#5660 item 8): opened beside a step, the finder asks with `step=`, so the engine marks that step's
    /// reader chosen and lists it first; the card says "In use for this step" and offers no Use for This Step.
    func testTheStepsReaderIsMarkedChosen() async throws {
        let chosenJSON = FinderJSON.shipped.replacingOccurrences(
            of: #""availability":"ships""#, with: #""chosen":true,"availability":"ships""#)
        FinderMockURLProtocol.reset { _ in (200, FinderJSON.list([chosenJSON, FinderJSON.found])) }
        let store = ModelFinderStore(client: makeClient())
        var query = Self.query
        query.step = "read-a-line"
        await store.load(query)
        let asked = try XCTUnwrap(FinderMockURLProtocol.requests(to: "/api/recipes/candidates").last)
        XCTAssertEqual(asked.query["step"], "read-a-line")
        XCTAssertTrue(ModelFinderCard.isChosen(try XCTUnwrap(store.candidates.first)))
        XCTAssertFalse(ModelFinderCard.isChosen(try XCTUnwrap(store.candidates.last)))
    }

    /// WHY (#5660 item 4): for Find names the person chooses who runs it: spaCy (in use), an MLX model to download,
    /// Apple Intelligence and Claude. One Fichero cannot run yet offers nothing to press and says why once; one that
    /// needs a provider first links to Settings › AI.
    func testWhoFindsNamesCardsSayWhatRuns() throws {
        let items = try JSONDecoder().decode([Components.Schemas.ModelCandidate].self, from: Data("""
        [{"id":"spacy:pkg/es_core_news_sm@bundled","name":"spaCy's small Spanish pipeline; bundled","source":"shipped",
          "offered_because":"a card that ships with Fichero","pin":{},"jobs":["find-names-tag-words"],"open_licence":true,
          "size":"16 MB","measured":"unmeasured","in_recipe_rules":true,"runs_where":"this_mac","chosen":true,
          "availability":"ships","availability_words":"Ships with Fichero"},
         {"id":"mlx:text/qwen3-4b@main","name":"Qwen3 4B Instruct","source":"installed",
          "offered_because":"an MLX text model this Mac can run","pin":{},"jobs":["find-names-tag-words"],
          "open_licence":true,"size":"2.3 GB","measured":"unmeasured","in_recipe_rules":false,"runs_where":"this_mac",
          "availability":"download","availability_words":"Download (2.3 GB)"},
         {"id":"apple:intelligence/foundation-models@os","name":"Apple Intelligence, on this Mac","source":"installed",
          "offered_because":"Apple's on-device model","pin":{},"jobs":["find-names-tag-words"],"open_licence":true,
          "size":"0 GB","measured":"unmeasured","in_recipe_rules":false,"runs_where":"this_mac",
          "refused":"Fichero cannot run it yet: Apple Intelligence is not available in this build or on this Mac",
          "availability":"not_here",
          "availability_words":"Fichero cannot run it yet (Apple Intelligence is not available in this build or on this Mac)"},
         {"id":"anthropic:claude@settings","name":"Claude (Anthropic), in the cloud","source":"installed",
          "offered_because":"a cloud model through your provider settings","pin":{},"jobs":["find-names-tag-words"],
          "open_licence":true,"size":"0 GB","measured":"unmeasured","in_recipe_rules":false,"runs_where":"provider",
          "refused":"Fichero cannot run it yet: add Claude (Anthropic) in Settings › AI first","availability":"not_here",
          "availability_words":"Fichero cannot run it yet (add Claude (Anthropic) in Settings › AI first)"}]
        """.utf8))
        let byName = Dictionary(uniqueKeysWithValues: items.map { ($0.id, $0) })
        let spacy = try XCTUnwrap(byName["spacy:pkg/es_core_news_sm@bundled"])
        let mlx = try XCTUnwrap(byName["mlx:text/qwen3-4b@main"])
        let apple = try XCTUnwrap(byName["apple:intelligence/foundation-models@os"])
        let claude = try XCTUnwrap(byName["anthropic:claude@settings"])
        XCTAssertTrue(ModelFinderCard.isChosen(spacy))
        XCTAssertFalse(ModelFinderCard.cannotRunHere(spacy))
        XCTAssertFalse(ModelFinderCard.cannotRunHere(mlx))
        XCTAssertEqual(ModelFinderCard.facts(mlx), "Download (2.3 GB)")
        XCTAssertTrue(ModelFinderCard.cannotRunHere(apple))
        XCTAssertFalse(ModelFinderCard.asksForSettings(apple), "nothing in Settings makes Apple Intelligence run")
        XCTAssertTrue(ModelFinderCard.cannotRunHere(claude))
        XCTAssertTrue(ModelFinderCard.asksForSettings(claude), "add Claude in Settings › AI first: linked")
        XCTAssertTrue(ModelFinderCard.offersUse(spacy) && ModelFinderCard.offersDownload(mlx))
        XCTAssertFalse(ModelFinderCard.offersUse(claude) || ModelFinderCard.offersDownload(claude))
    }

    /// WHY (shots5, 2026-10-11): Qwen2.5-VL 7B showed Download and Use for This Step beside "this Mac does not have
    /// the memory to run it alongside macOS and Fichero". A card the rules refused offers neither, following the
    /// engine's `refused`; a licence is the one refusal a press answers; one that runs elsewhere keeps its Download.
    func testARefusedCardOffersNoUseNorDownload() throws {
        func card(_ refused: String?, availability: String = "download") throws -> Components.Schemas.ModelCandidate {
            let why = refused.map { #","refused":"\#($0)""# } ?? ""
            return try JSONDecoder().decode(Components.Schemas.ModelCandidate.self, from: Data("""
            {"id":"mlx:hf/qwen@main","name":"Qwen2.5-VL 7B (OCR)","source":"installed","offered_because":"fits",
             "pin":{},"jobs":["find-names-tag-words"],"open_licence":true,"size":"5.7 GB","measured":"unmeasured",
             "in_recipe_rules":true,"runs_where":"this_mac","availability":"\(availability)",
             "availability_words":"Download (5.7 GB)",
             "download":{"runtime":"mlx","model":"qwen","action":"model.download","params":{}}\(why)}
            """.utf8))
        }
        let memory = try card("this Mac does not have the memory to run it alongside macOS and Fichero")
        XCTAssertFalse(ModelFinderCard.offersUse(memory))
        XCTAssertFalse(ModelFinderCard.offersDownload(memory))
        let fits = try card(nil)
        XCTAssertTrue(ModelFinderCard.offersUse(fits) && ModelFinderCard.offersDownload(fits))
        let licence = try card("its licence is not open (accept it to use it)")
        XCTAssertTrue(ModelFinderCard.offersUse(licence), "choosing it accepts the licence")
        let elsewhere = try card("this Mac does not have the memory to run it alongside macOS and Fichero",
                                 availability: "elsewhere")
        XCTAssertFalse(ModelFinderCard.offersUse(elsewhere))
        XCTAssertTrue(ModelFinderCard.offersDownload(elsewhere), "it runs on a machine of yours")
    }

    /// WHY (#5612): Find a Reader… is offered on the steps the engine's registry says read the material
    /// (`reads_material`), not on a list of job ids the app keeps and would let drift.
    func testReaderStepsComeFromTheJobRegistry() async throws {
        FinderMockURLProtocol.reset { request in
            guard request.url?.path == "/api/recipes/jobs" else { return (404, "{}") }
            func job(_ id: String, _ reads: Bool) -> String {
                """
                {"id":"\(id)","name":"\(id)","description":"","topic":"\(id)","layer":"reading","takes":[],
                 "gives":[],"compare":"","settings":[],"since":"2026.10.03","reads_material":\(reads)}
                """
            }
            let items = [job("read-a-page", true), job("transcribe-speech", true), job("correct", false)]
            return (200, "{\"items\":[\(items.joined(separator: ","))],\"count\":3}")
        }
        let setup = RecipeSetupStore(client: makeClient())
        await setup.loadJobs()
        XCTAssertTrue(setup.readsMaterial("read-a-page"))
        XCTAssertTrue(setup.readsMaterial("transcribe-speech"), "the registry's word, not a list kept here")
        XCTAssertFalse(setup.readsMaterial("correct"))
        XCTAssertFalse(setup.readsMaterial("unknown-job"))
    }

    /// WHY (`source.find.app-card-actions`, #5612): Use for This Step works on ANY candidate, not only
    /// the Start plan's installed offer: it sends the step and the card to use-candidate, setup's one
    /// code path, and a refusal is shown rather than swallowed.
    func testUseForStepPostsAnyCandidateToUseCandidate() async throws {
        FinderMockURLProtocol.reset { request in
            if request.url?.path == "/api/recipes/project/steps/use-candidate" {
                // The recorder has already read the body stream (it can be read once), so the second press
                // (the 'lines' step) is the refused one by its order, not by re-reading its body.
                if FinderMockURLProtocol.requests(to: "/api/recipes/project/steps/use-candidate").count > 1 {
                    return (422, #"{"detail":"Example OCR does not do the step 'lines' (find-lines)"}"#)
                }
                return (200, #"{"answers":null,"recipe":null}"#)
            }
            return (200, FinderJSON.list([FinderJSON.shipped, FinderJSON.found]))
        }
        let client = makeClient()
        let store = ModelFinderStore(client: client)
        await store.load(Self.query)
        let found = try XCTUnwrap(store.candidates.last)
        let setup = RecipeSetupStore(client: client)

        await setup.useCandidate(found, forStep: "read")

        let posts = FinderMockURLProtocol.requests(to: "/api/recipes/project/steps/use-candidate")
        XCTAssertEqual(posts.count, 1)
        XCTAssertEqual(posts.first?.method, "POST")
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: posts.first?.body ?? Data()) as? [String: Any])
        XCTAssertEqual(body["step"] as? String, "read")
        XCTAssertEqual(body["card"] as? String, "mlx:hf/example/ocr-mlx@main")
        XCTAssertNil(setup.errorMessage)
        XCTAssertEqual(setup.choiceRevision, 1, "an accepted choice moves the revision the finder reads again on")

        await setup.useCandidate(found, forStep: "lines")
        XCTAssertEqual(setup.choiceRevision, 1, "a refused choice moves nothing")
        XCTAssertEqual(FinderMockURLProtocol.requests(to: "/api/recipes/project/steps/use-candidate").count, 2)
        XCTAssertTrue(setup.errorMessage?.contains("Example OCR") == true, setup.errorMessage ?? "no refusal shown")
    }

    /// WHY (`source.onboard.new-project-inherits-the-cloud-setting`): a project that has not answered starts from the app's
    /// yes, as the ENGINE says it (`cloud_inherited`); the app keeps no copy of the rule, and one that answered keeps its own.
    func testANewProjectStartsFromTheCloudSettingTheEngineReports() async throws {
        func serve(project: String) {
            FinderMockURLProtocol.reset { request in
                request.url?.path == "/api/recipes/project" ? (200, project) : (200, "{}")
            }
        }
        serve(project: #"{"answers":null,"recipe":null,"cloud_inherited":true}"#)
        let inheriting = RecipeSetupStore(client: makeClient())
        await inheriting.loadSaved()
        XCTAssertTrue(inheriting.cloudAllowed)

        serve(project: #"{"answers":null,"recipe":null,"cloud_inherited":false}"#)
        let closed = RecipeSetupStore(client: makeClient())
        await closed.loadSaved()
        XCTAssertFalse(closed.cloudAllowed)

        serve(project: #"{"answers":{"cloud_allowed":false},"recipe":null,"cloud_inherited":false}"#)
        let answered = RecipeSetupStore(client: makeClient())
        await answered.loadSaved()
        XCTAssertFalse(answered.cloudAllowed, "a project that answered no stays no")
    }

    /// WHY (## 1102): the inherited yes is shown, never saved. A first ordinary Set Up save while the project only
    /// inherits sends no `cloud_allowed` (else the app's setting freezes as the project's own answer); once the person
    /// has answered, it is sent.
    func testASaveSendsCloudAllowedOnlyOnceTheProjectHasAnswered() async throws {
        func put() throws -> [String: Any] {
            let body = try XCTUnwrap(FinderMockURLProtocol.requests(to: "/api/recipes/project").last { $0.method == "PUT" }?.body)
            let sent = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
            return try XCTUnwrap(sent["answers"] as? [String: Any])
        }
        FinderMockURLProtocol.reset { request in
            request.url?.path == "/api/recipes/project"
                ? (200, #"{"answers":null,"recipe":null,"cloud_inherited":true}"#) : (200, "{}")
        }
        let store = RecipeSetupStore(client: makeClient())
        await store.loadSaved()
        XCTAssertTrue(store.cloudAllowed, "shown as the app's setting")
        XCTAssertFalse(store.cloudAnswered)
        _ = await store.save()
        XCTAssertNil(try put()["cloud_allowed"], "the inherited yes is not the project's answer")

        store.cloudChoice = true
        _ = await store.save()
        XCTAssertEqual(try put()["cloud_allowed"] as? Bool, true, "the person's own answer is sent")
    }

    /// ## 1103: a default pick is marked chosen but saved nowhere, so Use for This Step stays on it; the step's saved reader
    /// has none.
    func testUseForThisStepStaysOnADefaultPickButNotOnASavedReader() async throws {
        func card(chosen: Bool, defaultPick: Bool) async throws -> Components.Schemas.ModelCandidate {
            let json = FinderJSON.shipped.dropLast() + #","chosen":\#(chosen),"default_pick":\#(defaultPick)}"#
            FinderMockURLProtocol.reset { _ in (200, FinderJSON.list([String(json)])) }
            let store = ModelFinderStore(client: makeClient())
            await store.load(Self.query)
            return try XCTUnwrap(store.candidates.first)
        }
        XCTAssertFalse(ModelFinderCard.offersUseForThisStep(try await card(chosen: true, defaultPick: false)), "the saved reader")
        XCTAssertTrue(ModelFinderCard.offersUseForThisStep(try await card(chosen: true, defaultPick: true)), "a default: Use saves it")
        XCTAssertTrue(ModelFinderCard.offersUseForThisStep(try await card(chosen: false, defaultPick: false)))
    }
}
