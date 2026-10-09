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
     "runs_where":"this_mac"}
    """
    static let found = """
    {"id":"mlx:hf/example/ocr-mlx@main","name":"Example OCR","source":"hugging-face",
     "offered_because":"reads handwriting; lists Spanish","pin":{"hf":"example/ocr-mlx","revision":"main"},
     "jobs":["read-a-line"],"licence":"cc-by-nc-4.0","open_licence":false,"size":"size not stated",
     "measured":"unmeasured on your pages until a bake-off measures it","in_recipe_rules":true,"rule_rank":2,
     "installed":false,"runs_where":"this_mac",
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

    /// WHY (`source.find.app-card-says`, #5612): the card says, in words, whether the model is already
    /// here and where it runs, from the engine's `installed` and `runs_where`; nothing when the engine
    /// says nothing (a Kraken reader the run fetches).
    func testCardSaysWhetherItIsHereAndWhereItRuns() async throws {
        FinderMockURLProtocol.reset { _ in (200, FinderJSON.list([FinderJSON.shipped, FinderJSON.found])) }
        let store = ModelFinderStore(client: makeClient())
        await store.load(Self.query)
        let shipped = try XCTUnwrap(store.candidates.first)
        let found = try XCTUnwrap(store.candidates.last)
        XCTAssertEqual(ModelFinderCard.facts(found),
                       "Found on Hugging Face · size not stated · Not on this Mac yet · Runs on this Mac · licence: cc-by-nc-4.0")
        XCTAssertEqual(ModelFinderCard.facts(shipped), "Ships with Fichero · 0.02 GB · Runs on this Mac")
        XCTAssertEqual(ModelFinderStore.installedWords(true), "On this Mac")
        XCTAssertEqual(ModelFinderStore.placeWords("own_machine"), "Runs on a machine of yours")
        XCTAssertEqual(ModelFinderStore.placeWords("provider"), "Runs at the provider")
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

        await setup.useCandidate(found, forStep: "lines")
        XCTAssertEqual(FinderMockURLProtocol.requests(to: "/api/recipes/project/steps/use-candidate").count, 2)
        XCTAssertTrue(setup.errorMessage?.contains("Example OCR") == true, setup.errorMessage ?? "no refusal shown")
    }
}
