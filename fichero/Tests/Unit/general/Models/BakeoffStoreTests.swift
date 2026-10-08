//
//  BakeoffStoreTests.swift
//  FicheroTests
//
//  Check on your pages, setup's bake-off for the reading step
//  (`source.try.bakeoff-is-the-same-tool`, section 8a of
//  source/models-chains-and-projects.md; #4951). The engine runs the one evaluation job,
//  ranks and keeps the comparison; the app starts it, reads it back, shows it in the engine's
//  order and sends Use This. These drive `BakeoffStore` through the generated client against a
//  stub scoped to /api/recipes, so they never race other suites' requests (#4024).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class BakeoffMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?
    /// Every request that reached the stub, in order: method, path and JSON body.
    nonisolated(unsafe) static var seen: [(method: String, path: String, body: [String: Any])] = []
    override static func canInit(with request: URLRequest) -> Bool {
        (request.url?.path ?? "").contains("/api/recipes")
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        var body: [String: Any] = [:]
        if let stream = request.httpBodyStream {
            stream.open()
            var data = Data()
            var buffer = [UInt8](repeating: 0, count: 4096)
            // Until the stream ends, not while `hasBytesAvailable`: that can be false before the
            // client's writer thread has put the first bytes in (#5607).
            while true {
                let count = stream.read(&buffer, maxLength: buffer.count)
                guard count > 0 else { break }
                data.append(buffer, count: count)
            }
            stream.close()
            body = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
        } else if let data = request.httpBody {
            body = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
        }
        Self.seen.append((request.httpMethod ?? "", request.url?.path ?? "", body))
        guard let handler = Self.requestHandler else {
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
struct BakeoffStoreTests {

    private func makeClient(handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)) -> FicheroClient {
        BakeoffMockURLProtocol.requestHandler = handler
        BakeoffMockURLProtocol.seen = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [BakeoffMockURLProtocol.self]
        return FicheroClient(
            baseURL: URL(string: "https://test.fichero")!,
            libraryPath: "/tmp/test.fichero",
            session: URLSession(configuration: configuration)
        )
    }

    private static func reply(_ request: URLRequest, _ status: Int, _ json: String) -> (HTTPURLResponse, Data) {
        let response = HTTPURLResponse(
            url: request.url!, statusCode: status, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
        return (response, Data(json.utf8))
    }

    private static func row(rank: Int, card: String, name: String? = nil, reader: String = "kraken",
                            ruleRank: Int? = 1, local: Bool = true, cer: Double?, why: String? = nil) -> String {
        """
        {"rank":\(rank),"card":"\(card)","name":"\(name ?? "Reader \(card.uppercased())")","role":"\(ruleRank == nil ? "baseline for print" : "rule rank")",
         "rule_rank":\(ruleRank.map(String.init) ?? "null"),"reader":"\(reader)","model":"m-\(card)",
         "runs_on":"\(local ? "this-mac" : "cloud")","local":\(local),
         "cer":\(cer.map { "\($0)" } ?? "null"),"policy":\(cer == nil ? "null" : "\"diplomatic\""),
         "scores":{},"per_page":[],"pages_per_hour":\(cer == nil ? "null" : "400"),"seconds":null,
         "cost_usd":{"value":0,"basis":"measured","from":"runs on this Mac"},
         "carbon_g_per_page":null,"trainable":true,"size_gb":0.02,"why":\(why.map { "\"\($0)\"" } ?? "null")}
        """
    }

    private static func comparison(state: String, rows: [String]) -> String {
        """
        {"id":"job-7","job_id":"job-7","step":"read-a-line","started_at":"2026-10-05T10:00:00Z",
         "state":"\(state)","reason":null,
         "pages":[{"document_id":"p1","name":"f. 1r","lines":61},{"document_id":"p2","name":"f. 1v","lines":58}],
         "left_out":[],"lines":119,"rows":[\(rows.joined(separator: ","))],"winner":null}
        """
    }

    /// The engine's readiness as `GET …/bakeoffs` reports it: enough corrected lines, or how many more.
    private static func readinessJSON(lines: Int = 119, pages: Int = 2) -> String {
        let moreLines = max(0, 100 - lines), morePages = max(0, 2 - pages)
        let ready = moreLines == 0 && morePages == 0
        let sentence = ready ? "null"
            : "\"The bake-off needs at least 100 corrected lines on at least 2 pages; there are \(lines) on \(pages) page. Correct \(moreLines) more corrected lines, and it will be offered again.\""
        return """
        {"ready":\(ready),"lines":\(lines),"pages":\(pages),"min_lines":100,"min_pages":2,
         "more_lines":\(moreLines),"more_pages":\(morePages),"sentence":\(sentence)}
        """
    }

    private static func list(_ rows: [String]?, readiness: String? = nil) -> String {
        let items = rows.map { "[\(comparison(state: "done", rows: $0))]" } ?? "[]"
        return #"{"items":\#(items),"readiness":\#(readiness ?? readinessJSON())}"#
    }

    private static let recipeJSON = """
    {"id":"generated","title":"Spanish handwriting","purposes":["transcribe"],
     "steps":[
       {"id":"lines","job":"find-lines","runs_on":"this-mac","reasons":[],
        "card":{"id":"kraken-blla","note":"Kraken's built-in line finder"}},
       {"id":"read","job":"read-a-line","runs_on":"this-mac","reasons":[],
        "card":{"id":"kraken-mccatmus","note":"McCATMuS, many hands"}}],
     "gaps":[],"problems":[]}
    """

    /// WHY: below 100 corrected lines on two pages the engine refuses in words and runs
    /// nothing (`source.onboard.bakeoff-minimum`). Section 7b rules a problem is shown once, in
    /// words, and the person carries on; if the store dropped the engine's sentence the person
    /// would not know how many more lines to correct, and if it kept offering the button they
    /// would press it again and again for the same refusal.
    @Test func belowThresholdShowsTheEnginesSentenceAndNoRunButton() async {
        let sentence = "The bake-off needs at least 100 corrected lines on at least 2 pages; there are 40 on 1 page. "
            + "Correct 60 more corrected lines and corrected lines on 1 more page, and it will be offered again."
        let client = makeClient { request in
            Self.reply(request, 422, #"{"detail":"\#(sentence)"}"#)
        }
        let store = BakeoffStore(client: client)

        let started = await store.start()

        #expect(!started)
        #expect(store.refusal == sentence)
        #expect(store.notReadySentence == sentence, "the refusal stands where the button was")
        #expect(!store.canRun, "a refused bake-off offers no button to run it again")
        #expect(store.comparison == nil)
        #expect(store.errorMessage == nil, "the refusal is said once, not again as an error")
    }

    /// WHY: the bake-off is a job in Activity, so the person may leave setup while it runs
    /// (section 8a). Starting must POST to the engine and keep the comparison it answers with,
    /// and reading it again must GET that same comparison by id, so the table fills in as the
    /// job scores each reader rather than staying at "running" for ever.
    @Test func startPostsAndThenReadsTheResult() async throws {
        let running = Self.comparison(state: "running", rows: [
            Self.row(rank: 1, card: "kraken-catmus", cer: nil, why: "waiting for the evaluation job to score it")
        ])
        let done = Self.comparison(state: "done", rows: [Self.row(rank: 1, card: "kraken-catmus", cer: 0.042)])
        let client = makeClient { request in
            switch (request.httpMethod, request.url?.path) {
            case ("POST", "/api/recipes/project/bakeoffs"): Self.reply(request, 200, running)
            case ("GET", "/api/recipes/project/bakeoffs/job-7"): Self.reply(request, 200, done)
            default: Self.reply(request, 404, #"{"detail":"unexpected"}"#)
            }
        }
        let store = BakeoffStore(client: client)

        #expect(await store.start())
        #expect(store.isRunning)
        #expect(!store.canRun, "no second run while one is under way")

        await store.refresh()

        let calls = BakeoffMockURLProtocol.seen.map { "\($0.method) \($0.path)" }
        #expect(calls == ["POST /api/recipes/project/bakeoffs", "GET /api/recipes/project/bakeoffs/job-7"])
        #expect(store.comparison?.state == "done")
        #expect(!store.isRunning)
        let first = try #require(store.comparison?.rows.first)
        #expect(BakeoffStore.errorRate(first) == 0.042.formatted(.percent.precision(.fractionLength(1))))
    }

    /// WHY: the engine ranks by the fixed order (accuracy in one-point bands, then local before
    /// remote, cheaper, faster, …), which is not the order of the error rates or the names. If
    /// the app re-sorted the rows, the table would contradict the engine's winner and the
    /// recipe's measurements; rows must keep the engine's order exactly.
    @Test func rowsKeepTheEnginesOrder() async {
        // Two readers tied within a point: the local one first although its CER is higher.
        let rows = [
            Self.row(rank: 1, card: "zeta-local", ruleRank: 2, cer: 0.050),
            Self.row(rank: 2, card: "alpha-cloud", reader: "vision", ruleRank: 1, local: false, cer: 0.045),
            Self.row(rank: 3, card: "mid-reader", ruleRank: 3, cer: 0.120)
        ]
        let client = makeClient { request in Self.reply(request, 200, Self.list(rows)) }
        let store = BakeoffStore(client: client)

        await store.loadLatest()

        #expect(store.comparison?.rows.map(\.card) == ["zeta-local", "alpha-cloud", "mid-reader"])
        #expect(store.comparison?.rows.map(\.rank) == [1, 2, 3])
    }

    /// WHY: a candidate the evaluation cannot score here (not on this Mac, a remote model) is
    /// named with why, never silently dropped (`recipes/bakeoff.py`). The table must show that
    /// reason and no error rate, must not offer Use This for it (the engine refuses an unscored
    /// choice), and must name it in words, never by its card id (section 7b: never a raw id).
    @Test func aCandidateWithoutAScoreShowsItsReason() async throws {
        let why = "not on this Mac: download it to score it"
        let rows = [Self.row(rank: 1, card: "kraken-catmus", cer: 0.04),
                    Self.row(rank: 2, card: "kraken-tridis", name: "TRIDIS, medieval documentary hands",
                             ruleRank: 2, cer: nil, why: why)]
        let client = makeClient { request in Self.reply(request, 200, Self.list(rows)) }
        let store = BakeoffStore(client: client)
        await store.loadLatest()

        let unscored = try #require(store.comparison?.rows.last)
        #expect(BakeoffStore.note(unscored) == why)
        #expect(BakeoffStore.errorRate(unscored) == "—")
        let scored = try #require(store.comparison?.rows.first)
        #expect(BakeoffStore.note(scored).isEmpty, "a scored reader has no 'why not scored' note")
        let name = BakeoffStore.name(of: unscored)
        #expect(!name.contains("kraken-tridis"), "a candidate is never named by its card id")
        #expect(name == "TRIDIS, medieval documentary hands", "named by its card's own name, as the engine sends it")

        // Use This is not sent for an unscored candidate.
        let setup = RecipeSetupStore(client: client)
        #expect(await store.use(unscored, scope: .project, in: setup) == false)
        #expect(!BakeoffMockURLProtocol.seen.contains { $0.path.hasSuffix("/use") })
    }

    /// WHY: Use This makes the winner the reading step's reader for the scope the person picks,
    /// the project or one folder (section 8a, `source.try.use-this-scope`). The store must send
    /// the card and the scope (and the folder for a folder), and the reading step the person is
    /// looking at must then show the engine's new reader in place, leaving every other step as
    /// it was; otherwise setup would go on showing (and saving back) the reader it replaced.
    @Test func useThisPostsTheScopeAndUpdatesTheStep() async throws {
        let rows = [Self.row(rank: 1, card: "kraken-catmus", cer: 0.04)]
        let saved = """
        {"answers":{"purposes":["transcribe"]},
         "recipe":{"id":"generated","title":"Spanish handwriting","purposes":["transcribe"],
          "steps":[
            {"id":"lines","job":"find-lines","runs_on":"this-mac","reasons":[],
             "card":{"id":"kraken-blla","note":"Kraken's built-in line finder"}},
            {"id":"read","job":"read-a-line","runs_on":"this-mac","reasons":["chosen in the bake-off"],
             "card":{"id":"kraken-catmus","note":"CATMuS medieval"}}],
          "gaps":[],"problems":[],
          "overrides":[{"step":"read","scope":"folder","folder_id":"f1","card":"kraken-catmus"}]}}
        """
        let client = makeClient { request in
            switch (request.httpMethod, request.url?.path) {
            case ("GET", "/api/recipes/project/bakeoffs"):
                Self.reply(request, 200, Self.list(rows))
            case ("PUT", "/api/recipes/project"):
                Self.reply(request, 200, #"{"answers":{},"recipe":\#(Self.recipeJSON)}"#)
            case ("POST", "/api/recipes/project/bakeoffs/job-7/use"):
                Self.reply(request, 200, saved)
            default:
                Self.reply(request, 404, #"{"detail":"unexpected"}"#)
            }
        }
        let store = BakeoffStore(client: client)
        await store.loadLatest()
        let setup = RecipeSetupStore(client: client)
        setup.adoptEngineRecipe(Data(Self.recipeJSON.utf8))
        let linesBefore = try #require(setup.recipe?.steps.first)

        let row = try #require(store.comparison?.rows.first)
        #expect(await store.use(row, scope: .folder(id: "f1"), in: setup))

        let use = try #require(BakeoffMockURLProtocol.seen.last { $0.path.hasSuffix("/use") })
        #expect(use.body["card"] as? String == "kraken-catmus")
        #expect(use.body["scope"] as? String == "folder")
        #expect(use.body["folder_id"] as? String == "f1")
        // The recipe on screen was saved first, so the engine set the reader on that recipe.
        let order = BakeoffMockURLProtocol.seen.map { "\($0.method) \($0.path)" }
        #expect(order.firstIndex(of: "PUT /api/recipes/project")! < order.firstIndex(of: "POST /api/recipes/project/bakeoffs/job-7/use")!)

        let read = try #require(setup.recipe?.steps.first { $0.job == "read-a-line" })
        #expect(read.card?.id == "kraken-catmus")
        #expect(read.card?.note == "CATMuS medieval")
        #expect(setup.recipe?.steps.first == linesBefore, "a step Use This did not change is left as it was")
        #expect(BakeoffStore.name(of: row) == "Reader KRAKEN-CATMUS", "the chosen reader is named by the name its row carries")

        // A later save sends the engine's override back, so Continue never drops the choice.
        BakeoffMockURLProtocol.seen = []
        #expect(await setup.save())
        let put = try #require(BakeoffMockURLProtocol.seen.last { $0.method == "PUT" })
        let overrides = (put.body["recipe"] as? [String: Any])?["overrides"] as? [[String: Any]]
        #expect(overrides?.first?["folder_id"] as? String == "f1")
    }

    /// WHY: for the project scope the body names the project and no folder; the engine refuses
    /// a folder scope with no folder, and a stray folder id would set the wrong scope.
    @Test func useThisForTheProjectSendsNoFolder() async throws {
        let rows = [Self.row(rank: 1, card: "kraken-catmus", cer: 0.04)]
        let client = makeClient { request in
            switch (request.httpMethod, request.url?.path) {
            case ("GET", _): Self.reply(request, 200, Self.list(rows))
            default: Self.reply(request, 200, #"{"answers":{},"recipe":\#(Self.recipeJSON)}"#)
            }
        }
        let store = BakeoffStore(client: client)
        await store.loadLatest()
        let row = try #require(store.comparison?.rows.first)

        #expect(await store.use(row, scope: .project, in: RecipeSetupStore(client: client)))

        let use = try #require(BakeoffMockURLProtocol.seen.last { $0.path.hasSuffix("/use") })
        #expect(use.body["scope"] as? String == "project")
        #expect(use.body["folder_id"] == nil)
    }

    // MARK: The gaps the app found (2026-10-05)

    /// WHY: section 7b rules a reader is never shown by a raw model id. The engine's row carries
    /// the card's own name (the name the reading step shows for its model), so every reader in
    /// the table, not only the one already in the recipe, is named in words; the app no longer
    /// makes up "Kraken reader, the rules' 2nd choice". Only a row with no name (a card no longer
    /// shipped) falls back to its kind, still never its id.
    @Test func everyRowIsNamedByItsCardsName() async throws {
        let rows = [
            Self.row(rank: 1, card: "kraken:zenodo/10.5281/zenodo.12743230@unpinned",
                     name: "CATMuS Medieval, medieval manuscripts (French, Latin, Spanish)", ruleRank: 2, cer: 0.04),
            Self.row(rank: 2, card: "kraken:zenodo/10.5281/zenodo.13788177@unpinned",
                     name: "McCATMuS, general Latin-script recognition, 16th-21st century", ruleRank: 1, cer: 0.06),
            Self.row(rank: 3, card: "kraken:zenodo/gone@1", name: "", ruleRank: 3, cer: nil, why: "gone")
        ]
        let client = makeClient { request in Self.reply(request, 200, Self.list(rows)) }
        let store = BakeoffStore(client: client)
        await store.loadLatest()

        let names = try #require(store.comparison?.rows).map(BakeoffStore.name(of:))
        #expect(names == ["CATMuS Medieval, medieval manuscripts (French, Latin, Spanish)",
                          "McCATMuS, general Latin-script recognition, 16th-21st century",
                          "A Kraken reader"])
        #expect(!names.contains { $0.contains("zenodo") || $0.contains("choice") },
                "no card id, and no name made up from the rules' place")
    }

    /// WHY: below 100 corrected lines on two pages the bake-off cannot run
    /// (`source.onboard.bakeoff-minimum`). The person must read how many more lines to correct
    /// before pressing anything, and must not be offered a button the engine would refuse; the
    /// engine's readiness (counted as its start counts) decides both. Nothing is started.
    @Test func readinessIsSaidBeforePressingAndTheButtonWaits() async {
        var readiness = Self.readinessJSON(lines: 44, pages: 1)
        let client = makeClient { request in Self.reply(request, 200, Self.list(nil, readiness: readiness)) }
        let store = BakeoffStore(client: client)
        #expect(!store.canRun, "no button before the engine has said there are enough corrected lines")

        await store.loadLatest()

        #expect(store.readiness?.ready == false)
        #expect(store.readiness?.moreLines == 56 && store.readiness?.morePages == 1)
        let sentence = store.notReadySentence ?? ""
        #expect(sentence.hasPrefix("The bake-off needs at least 100 corrected lines"),
                "the engine's sentence is shown before anything is pressed")
        #expect(!store.canRun, "Compare Readers is hidden until there are enough")
        #expect(!BakeoffMockURLProtocol.seen.contains { $0.method == "POST" }, "nothing was started")

        readiness = Self.readinessJSON(lines: 132, pages: 3)
        await store.loadLatest()

        #expect(store.readiness?.ready == true)
        #expect(store.notReadySentence == nil)
        #expect(store.canRun, "offered again once there are enough corrected lines")
    }
}
