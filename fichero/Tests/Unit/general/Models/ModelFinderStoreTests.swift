//
//  ModelFinderStoreTests.swift
//  FicheroTests
//
//  The model finder (#5611, `source.find.app-*`): the store reads the engine's candidates
//  through the generated client, follows the online search through Activity's job list (never a
//  poller of its own), downloads a found reader through the one download route, and Use for This
//  Step sends the plan's own offer through setup's use-instead. Driven through the generated client
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
     "measured":"unmeasured on your pages until a bake-off measures it","in_recipe_rules":true,"rule_rank":1}
    """
    static let found = """
    {"id":"mlx:hf/example/ocr-mlx@main","name":"Example OCR","source":"hugging-face",
     "offered_because":"reads handwriting; lists Spanish","pin":{"hf":"example/ocr-mlx","revision":"main"},
     "jobs":["read-a-line"],"licence":"cc-by-nc-4.0","open_licence":false,"size":"size not stated",
     "measured":"unmeasured on your pages until a bake-off measures it","in_recipe_rules":true,"rule_rank":2}
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

    /// WHY (`source.find.app-card-actions`): Download goes through the one download route by the repo
    /// the engine pinned, so the found reader lands in the model store the rules read; a shipped card
    /// has no Download here (its pin is not a download id the route accepts).
    func testDownloadPostsTheFoundReadersRepoToTheDownloadRoute() async throws {
        FinderMockURLProtocol.reset { request in
            if request.url?.path.hasPrefix("/api/local-models/download") == true {
                return (200, #"{"status":"queued","model_type":"mlx","model_id":"example/ocr-mlx","job_id":"dl-1"}"#)
            }
            return (200, FinderJSON.list([FinderJSON.shipped, FinderJSON.found]))
        }
        let store = ModelFinderStore(client: makeClient())
        await store.load(Self.query)
        let shipped = try XCTUnwrap(store.candidates.first)
        let found = try XCTUnwrap(store.candidates.last)
        XCTAssertNil(ModelFinderStore.downloadRepo(of: shipped))

        await store.download(found)

        let posts = FinderMockURLProtocol.requests(to: "/api/local-models/download/mlx/example/ocr-mlx")
        XCTAssertEqual(posts.count, 1)
        XCTAssertEqual(posts.first?.method, "POST")
        XCTAssertTrue(store.downloading.contains(found.id))
        XCTAssertNil(store.errorMessage)
    }

    /// WHY (`source.find.app-card-actions`): Use for This Step is offered only where the Start plan
    /// offers that installed reader instead of the step's download, and sends exactly that offer
    /// (the download's model and the card) to use-instead, setup's one code path.
    func testUseForStepPostsThePlansOfferToUseInstead() async throws {
        FinderMockURLProtocol.reset { request in
            if request.url?.path == "/api/recipes/project/start/use-instead" {
                return (200, #"{"answers":null,"recipe":null}"#)
            }
            return (200, FinderJSON.list([FinderJSON.shipped, FinderJSON.found]))
        }
        let client = makeClient()
        let store = ModelFinderStore(client: client)
        await store.load(Self.query)
        let shipped = try XCTUnwrap(store.candidates.first)
        let found = try XCTUnwrap(store.candidates.last)
        let downloadJSON = """
        {"runtime":"mlx","model":"qwen-ocr","steps":["read"],"size_mb":5000,"action":"model.download",
         "params":{"runtime":"mlx","model":"qwen-ocr"},"name":"Qwen OCR",
         "instead":[{"card":"kraken:catmus@1","model":"catmus","name":"CATMuS Medieval","licence":""}]}
        """
        let download = try JSONDecoder().decode(Components.Schemas.StartDownload.self, from: Data(downloadJSON.utf8))

        XCTAssertNil(ModelFinderStore.insteadOffer(for: found, step: "read", downloads: [download]))
        XCTAssertNil(ModelFinderStore.insteadOffer(for: shipped, step: "lines", downloads: [download]))
        let offer = try XCTUnwrap(ModelFinderStore.insteadOffer(for: shipped, step: "read", downloads: [download]))

        let setup = RecipeSetupStore(client: client)
        await setup.useInstead(offer.download, offer.installed)

        let posts = FinderMockURLProtocol.requests(to: "/api/recipes/project/start/use-instead")
        XCTAssertEqual(posts.count, 1)
        XCTAssertEqual(posts.first?.method, "POST")
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: posts.first?.body ?? Data()) as? [String: Any])
        XCTAssertEqual(body["model"] as? String, "qwen-ocr")
        XCTAssertEqual(body["card"] as? String, "kraken:catmus@1")
    }
}
