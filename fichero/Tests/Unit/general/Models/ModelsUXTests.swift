//
//  ModelsUXTests.swift
//  FicheroTests
//
//  Set Up › Ready's model questions and the one download path (#5619, #5620), to the spec
//  (docs/contributor_manual/specs/source/models-chains-and-projects.md):
//  `source.find.choose-a-model-opens-the-finder` (a step's Choose a model… opens the finder for THAT step's
//  job) and `source.find.one-download-path` (one method, one route, a job Activity lists, its progress and its
//  failure said on the row that asked). Driven through the generated client against a stub scoped to this
//  suite's own host, recording what each path was sent.
//

@testable import Fichero
import FicheroAPIClient
import XCTest

private nonisolated struct DownloadRequest {
    let path: String
    let method: String
}

private final class DownloadsMockURLProtocol: URLProtocol {
    private static let lock = NSLock()
    nonisolated(unsafe) static var handler: ((URLRequest) -> (Int, String))?
    /// The download job's state and reason a handler answers with, so a test moves the job on without
    /// capturing state of its own.
    nonisolated(unsafe) static var jobState: (String, String?) = ("running", nil)
    nonisolated(unsafe) private static var log: [DownloadRequest] = []

    static func reset(_ handler: @escaping (URLRequest) -> (Int, String)) {
        lock.lock()
        self.handler = handler
        log = []
        jobState = ("running", nil)
        lock.unlock()
    }

    static func requests(to path: String) -> [DownloadRequest] {
        lock.lock()
        defer { lock.unlock() }
        return log.filter { $0.path == path }
    }

    // swiftlint:disable:next static_over_final_class
    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.host == "downloads.test"
    }

    // swiftlint:disable:next static_over_final_class
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url else { return }
        Self.lock.lock()
        Self.log.append(DownloadRequest(path: url.path, method: request.httpMethod ?? ""))
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

private nonisolated enum DownloadJSON {
    static let route = "/api/local-models/download/mlx/Qwen2.5-VL-7B"
    static let job = "/api/activity/jobs/dl-1"
    static let queued = #"{"status":"queued","model_type":"mlx","model_id":"Qwen2.5-VL-7B","job_id":"dl-1"}"#

    static func node(_ state: String, reason: String?) -> String {
        let said = reason.map { ",\"reason\":\"\($0)\"" } ?? ""
        return """
        {"id":"dl-1","kind":"download-model","name":"Download a model","subject":"mlx:Qwen2.5-VL-7B",
         "state":"\(state)"\(said),"done":0,"total":1}
        """
    }
}

@MainActor
final class ModelsUXTests: XCTestCase {
    private static let key = ModelDownloads.Key(runtime: "mlx", model: "Qwen2.5-VL-7B")
    private static let name = "Qwen2.5-VL 7B"

    private func makeClient() -> FicheroClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [DownloadsMockURLProtocol.self]
        return FicheroClient(
            baseURL: URL(string: "https://downloads.test")!,
            libraryPath: "/tmp/Marshall Diary 1940.fichero",
            session: URLSession(configuration: configuration)
        )
    }

    /// A store whose own follow never fires inside a test: each test reads the job when it says so.
    private func makeDownloads() -> ModelDownloads {
        ModelDownloads(client: makeClient(), followInterval: .seconds(3600))
    }

    override func tearDown() {
        DownloadsMockURLProtocol.handler = nil
        super.tearDown()
    }

    // MARK: source.find.one-download-path

    /// WHY (#5620): the maintainer pressed Download and nothing visible happened. The one method posts the one
    /// route, by runtime and model; the row then says what the job says, not a bare "Downloading…" forever; when
    /// the job is done the model is here and whoever lists models hears it once.
    func testStartPostsTheOneRouteAndTheRowSaysWhatTheJobSays() async throws {
        DownloadsMockURLProtocol.reset { request in
            switch request.url?.path ?? "" {
            case DownloadJSON.route: (200, DownloadJSON.queued)
            case DownloadJSON.job:
                (200, DownloadJSON.node(DownloadsMockURLProtocol.jobState.0, reason: DownloadsMockURLProtocol.jobState.1))
            default: (404, "{}")
            }
        }
        DownloadsMockURLProtocol.jobState = ("running", "Downloading Qwen2.5-VL 7B (OCR): 1.2 GB of 5.6 GB")
        let downloads = makeDownloads()
        var heard: [ModelDownloads.Key] = []
        downloads.onFinished = { heard.append($0) }

        await downloads.start(Self.key, name: Self.name)

        let posts = DownloadsMockURLProtocol.requests(to: DownloadJSON.route)
        XCTAssertEqual(posts.count, 1)
        XCTAssertEqual(posts.first?.method, "POST")
        XCTAssertTrue(downloads.isActive(Self.key))
        XCTAssertEqual(downloads.line(Self.key), "Waiting to download Qwen2.5-VL 7B…")

        let going = await downloads.refresh(Self.key)
        XCTAssertTrue(going)
        XCTAssertEqual(downloads.line(Self.key), "Downloading Qwen2.5-VL 7B (OCR): 1.2 GB of 5.6 GB")

        DownloadsMockURLProtocol.jobState = ("done", nil)
        let stillGoing = await downloads.refresh(Self.key)
        XCTAssertFalse(stillGoing)
        XCTAssertEqual(downloads.state(Self.key), .done)
        XCTAssertNil(downloads.line(Self.key), "a finished download leaves the row to say what the engine lists")
        XCTAssertFalse(downloads.isActive(Self.key))
        XCTAssertEqual(downloads.finished, 1)
        XCTAssertEqual(heard, [Self.key])
    }

    /// WHY: "a refusal before queueing, such as a model this Mac cannot run, is said at once": the engine's own
    /// words reach the row, never "HTTP 400" alone or nothing.
    func testARefusalSaysTheEnginesWords() async throws {
        DownloadsMockURLProtocol.reset { _ in
            (400, #"{"detail":"Qwen2.5-VL 7B needs 16 GB of memory; this Mac has 8 GB"}"#)
        }
        let downloads = makeDownloads()

        await downloads.start(Self.key, name: Self.name)

        XCTAssertFalse(downloads.isActive(Self.key))
        XCTAssertEqual(downloads.line(Self.key),
                       "Could not download Qwen2.5-VL 7B: Qwen2.5-VL 7B needs 16 GB of memory; this Mac has 8 GB")
        XCTAssertTrue(ModelFinderCard.failed(downloads.state(Self.key)), "the button offers to try again")
    }

    /// WHY: "a failure says why on the row, in the job's words".
    func testAFailedJobSaysWhy() async throws {
        DownloadsMockURLProtocol.reset { request in
            switch request.url?.path ?? "" {
            case DownloadJSON.route: (200, DownloadJSON.queued)
            case DownloadJSON.job:
                (200, DownloadJSON.node("failed", reason: "Qwen2.5-VL-7B did not download: the MLX runtime is not set up"))
            default: (404, "{}")
            }
        }
        let downloads = makeDownloads()
        await downloads.start(Self.key, name: Self.name)
        let going = await downloads.refresh(Self.key)

        XCTAssertFalse(going)
        XCTAssertEqual(downloads.line(Self.key),
                       "Could not download Qwen2.5-VL 7B: Qwen2.5-VL-7B did not download: the MLX runtime is not set up")
        XCTAssertEqual(downloads.finished, 0)
    }

    /// WHY: a second press while the first runs must not queue the model twice.
    func testASecondPressWhileItRunsSendsNothing() async throws {
        DownloadsMockURLProtocol.reset { request in
            request.url?.path == DownloadJSON.route ? (200, DownloadJSON.queued) : (404, "{}")
        }
        let downloads = makeDownloads()
        await downloads.start(Self.key, name: Self.name)
        await downloads.start(Self.key, name: Self.name)
        XCTAssertEqual(DownloadsMockURLProtocol.requests(to: DownloadJSON.route).count, 1)
    }

    /// WHY: the finder's Download goes through the same method (one path), keyed by the download the engine
    /// names, so the card and setup's To download first row say the same thing for the same model.
    func testTheFindersDownloadIsTheOneMethod() async throws {
        DownloadsMockURLProtocol.reset { request in
            request.url?.path == DownloadJSON.route ? (200, DownloadJSON.queued) : (404, "{}")
        }
        let downloads = makeDownloads()
        let finder = ModelFinderStore(client: makeClient(), downloads: downloads)
        let json = """
        {"id":"mlx:hf/mlx-community/Qwen2.5-VL-7B-Instruct-4bit@unpinned","name":"Qwen2.5-VL 7B",
         "source":"shipped","offered_because":"a card that ships with Fichero",
         "pin":{"hf":"mlx-community/Qwen2.5-VL-7B-Instruct-4bit","revision":"main"},"jobs":["correct"],
         "open_licence":true,"size":"5.6 GB","measured":"unmeasured","in_recipe_rules":true,"installed":false,
         "runs_where":"this_mac","download":{"runtime":"mlx","model":"Qwen2.5-VL-7B","action":"model.download",
         "params":{"runtime":"mlx","model":"Qwen2.5-VL-7B"}}}
        """
        let candidate = try JSONDecoder().decode(Components.Schemas.ModelCandidate.self, from: Data(json.utf8))
        XCTAssertEqual(ModelFinderStore.downloadKey(candidate), Self.key)

        await finder.download(candidate)

        XCTAssertTrue(downloads.isActive(Self.key), "setup's row for the same model sees it running")
        XCTAssertEqual(DownloadsMockURLProtocol.requests(to: DownloadJSON.route).count, 1)
    }

    /// WHY: Settings' catalog rows download through the same route: this Mac's MLX server's models as `mlx`,
    /// spaCy, Kraken and Whisper under their own names.
    func testSettingsCatalogRowsUseTheRoutesRuntimeNames() {
        XCTAssertEqual(ModelDownloads.runtime(ofProvider: "omlx"), "mlx")
        XCTAssertEqual(ModelDownloads.runtime(ofProvider: "spacy"), "spacy")
        XCTAssertEqual(ModelDownloads.runtime(ofProvider: "kraken"), "kraken")
        XCTAssertEqual(ModelDownloads.runtime(ofProvider: "whisper"), "whisper")
    }

    // MARK: source.find.choose-a-model-opens-the-finder

    /// WHY (#5619): Choose a model… did nothing. In setup, with a project, choosing, downloading or choosing a
    /// cloud model opens the finder for the step; letting pages leave and a licence stay setup's own; without a
    /// project there is no finder to open, so setup's handler answers.
    func testAModelFixOpensTheFinderForTheStep() {
        for fix in ["choose-model", "download", "choose-cloud"] {
            XCTAssertEqual(RecipeStepsView.fixRoute(fix, hasProject: true), .finder, fix)
            XCTAssertEqual(RecipeStepsView.fixRoute(fix, hasProject: false), .setup, fix)
        }
        XCTAssertEqual(RecipeStepsView.fixRoute("allow-cloud", hasProject: true), .setup)
        XCTAssertEqual(RecipeStepsView.fixRoute("accept-licence", hasProject: true), .setup)
    }

    /// WHY: the finder asks for THAT step's job with the project's answers, not a reader's job by default.
    func testTheFinderAsksForTheStepsJob() {
        let setup = RecipeSetupStore(client: makeClient())
        setup.scripts = ["Latn"]
        setup.languages = ["en"]
        setup.materials = ["print", "handwriting"]
        let query = setup.finderQuery(job: "find-statements")
        XCTAssertEqual(query.job, "find-statements")
        XCTAssertEqual(query.scripts, ["Latn"])
        XCTAssertEqual(query.languages, ["en"])
        XCTAssertEqual(query.material, "print")
        XCTAssertNil(setup.job(ofStepId: "statements"), "no recipe on screen: no step to open")
    }

    /// WHY: with nothing listed for a step that is not a reader's, the finder says where such a model comes
    /// from, not "Search Online" (the online search looks for readers only).
    func testNothingFoundSaysWhereATextModelComesFrom() {
        XCTAssertTrue(ModelFinderView.nothingFound(job: "read-a-line").contains("Search Online"))
        let statements = ModelFinderView.nothingFound(job: "find-statements")
        XCTAssertFalse(statements.contains("Search Online"))
        XCTAssertTrue(statements.contains("Ollama"))
    }
}
