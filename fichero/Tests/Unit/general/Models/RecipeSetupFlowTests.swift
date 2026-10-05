//
//  RecipeSetupFlowTests.swift
//  FicheroTests
//
//  Setup as a flow a person goes through (`source/models-chains-and-projects.md`
//  section 7): its screens in order, a purpose that reorders what is offered but
//  hides nothing, a language added later from the Inspector, and the way sources
//  come in (link, copy, move, index) reaching the engine's ingest call. Written
//  from `source.onboard.screens-in-order`, `source.onboard.offers-never-hides`,
//  `source.onboard.add-layer` and `source.sync.four-ways-in`, not from the code.
//
//  Through the real `RecipeSetupStore` and `ImportService` over the generated
//  client; only the transport is stubbed, on this suite's own session.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class SetupFlowURLProtocol: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) -> (Int, String))?
    /// Every request that reached the stub: method, path and JSON body.
    struct Seen { let method: String; let path: String; let body: [String: Any] }
    nonisolated(unsafe) static var seen: [Seen] = []

    override static func canInit(with request: URLRequest) -> Bool {
        let path = request.url?.path ?? ""
        return path.hasPrefix("/api/recipes") || path.hasPrefix("/api/ingest") || path.hasPrefix("/api/topics")
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

/// The engine is granted the folder without a real sandbox extension.
private final class AcceptingEngine: EngineAccessGranting {
    func grantAccess(toPath path: String, bookmark: Data) async throws {}
}

@MainActor
@Suite(.serialized)
struct RecipeSetupFlowTests {

    private func makeClient(_ handler: @escaping (URLRequest) -> (Int, String)) -> FicheroClient {
        SetupFlowURLProtocol.handler = handler
        SetupFlowURLProtocol.seen = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [SetupFlowURLProtocol.self]
        return FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/test.fichero",
                             session: URLSession(configuration: configuration))
    }

    private static func job(_ id: String, _ layer: String) -> String {
        #"{"id":"\#(id)","name":"\#(id)","description":"what \#(id) does","topic":"\#(id)","layer":"\#(layer)","#
            + #""takes":[],"gives":[],"compare":"","settings":[],"since":"1"}"#
    }

    /// The registry, in its own order.
    private static let jobsJSON = #"{"count":4,"items":["#
        + [job("find-lines", "lines"), job("read-a-line", "reading"), job("find-names-tag-words", "entities"),
           job("embed", "search")].joined(separator: ",") + "]}"

    private static func recipe(steps: [(String, String)]) -> String {
        let rendered = steps.map { #"{"id":"\#($0.0)","job":"\#($0.1)","reasons":[]}"# }.joined(separator: ",")
        return #"{"id":"generated","title":"t","purposes":["p"],"steps":[\#(rendered)],"gaps":[],"problems":[]}"#
    }

    // MARK: source.onboard.screens-in-order

    /// WHY (section 7b, ruled 2026-10-05): "where the project lives, then its files, then keeping
    /// it exported, then the purposes and the rest". Set Up… on an existing project starts at
    /// screen 2, Your material, because the project already lives somewhere. If a screen moved,
    /// a person would be asked what the project is for before saying where its files come from,
    /// or reach Start before seeing the recipe; if first run's list drifted from Set Up…'s, a new
    /// project and an existing one would be set up by two flows. (Kept exported, screen 3, is
    /// not built yet: #5485.)
    @Test("Set Up… starts at Your material, then What it is for, and ends at Start")
    func screensInOrder() {
        #expect(FirstRunStep.setUpSteps == [.material, .keptExported, .purpose, .about, .jobs, .recipe, .automatic, .start])
        let firstRun = FirstRunStep.steps(isCompanionPlatform: false)
        #expect(Array(firstRun.suffix(FirstRunStep.setUpSteps.count)) == FirstRunStep.setUpSteps)
        var walked = [FirstRunStep.setUpSteps[0]]
        while walked.last != .start { walked.append(walked.last!.next(in: FirstRunStep.setUpSteps)) }
        #expect(walked == FirstRunStep.setUpSteps, "Continue walks the screens in order and stops at Start")
    }

    /// WHY: setup "can be closed at any screen with the answers kept as a draft,
    /// and nothing runs before Start". Leaving every screen before Start saves the
    /// draft (PUT) and never posts Start; if a screen skipped the save, closing
    /// there would lose the answers; if any posted Start, work would begin
    /// before the person said yes.
    @Test("leaving each screen before Start keeps a draft and never starts")
    func everyScreenBeforeStartKeepsADraft() async {
        let store = RecipeSetupStore(client: makeClient { _ in (200, #"{"answers":{},"recipe":null}"#) })
        let draftScreens = FirstRunStep.setUpSteps.filter(\.savesDraft)
        #expect(draftScreens == [.material, .keptExported, .purpose, .about, .jobs, .recipe, .automatic], "every screen but Start saves")
        #expect(!FirstRunStep.start.savesDraft)
        for _ in draftScreens { #expect(await store.save()) }
        let calls = SetupFlowURLProtocol.seen.map { "\($0.method) \($0.path)" }
        #expect(calls == Array(repeating: "PUT /api/recipes/project", count: draftScreens.count))
    }

    // MARK: source.onboard.offers-never-hides

    /// WHY: "a purpose changes what is offered first ... every view and tool
    /// stays reachable in every project" (ruled 2026-10-01: offer first, never
    /// hide). Two purposes give two recipes; each puts its own steps first, and
    /// both still offer every job the registry knows. A purpose that dropped a
    /// job from the list would hide a tool the person may need.
    @Test("a purpose reorders what is offered first but never hides a job")
    func purposeReordersButNeverHides() async {
        var recipeJSON = Self.recipe(steps: [("read", "read-a-line"), ("names", "find-names-tag-words")])
        let store = RecipeSetupStore(client: makeClient { request in
            request.url?.path == "/api/recipes/jobs" ? (200, Self.jobsJSON) : (200, recipeJSON)
        })
        store.languages = ["es"]
        store.scripts = ["Latn"]
        await store.loadJobs()
        let everyJob = ["find-lines", "read-a-line", "find-names-tag-words", "embed"]

        store.purposes = ["entities"]
        await store.assemble()
        let entities = store.offeredJobs.map(\.id)
        #expect(entities == ["read-a-line", "find-names-tag-words", "find-lines", "embed"],
                "the recipe's steps first, in its order, then the rest in the registry's")

        recipeJSON = Self.recipe(steps: [])   // a tools purpose runs nothing by itself
        store.purposes = ["decipher"]
        await store.assemble()
        let decipher = store.offeredJobs.map(\.id)
        #expect(decipher == everyJob, "with nothing first, every job is still offered")
        #expect(Set(entities) == Set(everyJob) && Set(decipher) == Set(everyJob), "no purpose hides a job")
    }

    // MARK: source.onboard.add-layer (the language half)

    /// WHY: "a layer or a language can be added later from the library's
    /// Inspector". Adding a language must re-propose the recipe from the new
    /// answers and keep both on the project; if it only changed the field, the
    /// saved recipe would still be the one for the old languages, and if it
    /// started anything, adding a language would run work nobody asked for.
    @Test("a language added later re-proposes the recipe and keeps it, starting nothing")
    func languageAddedLater() async throws {
        let store = RecipeSetupStore(client: makeClient { request in
            switch (request.httpMethod, request.url?.path) {
            case ("GET", "/api/recipes/project"):
                return (200, #"{"answers":{"purpose":"transcribe","languages":["es"],"scripts":["Latn"]},"recipe":null}"#)
            case ("POST", "/api/recipes/assemble"):
                return (200, Self.recipe(steps: [("read", "read-a-line")]))
            default:
                return (200, #"{"answers":{},"recipe":null}"#)
            }
        })
        await store.loadSaved()

        let kept = await store.updateLanguages(store.languages + ["la"])

        #expect(kept)
        let assemble = try #require(SetupFlowURLProtocol.seen.first { $0.path == "/api/recipes/assemble" })
        #expect(assemble.body["languages"] as? [String] == ["es", "la"])
        let save = try #require(SetupFlowURLProtocol.seen.last { $0.method == "PUT" })
        let answers = try #require(save.body["answers"] as? [String: Any])
        #expect(answers["languages"] as? [String] == ["es", "la"])
        #expect(save.body["recipe"] is [String: Any], "the recipe for the new languages is kept with them")
        #expect(!SetupFlowURLProtocol.seen.contains { $0.path.hasSuffix("/start") }, "nothing starts")
    }

    // MARK: source.sync.four-ways-in

    /// WHY: setup asks how sources come in (link, copy, move or index, ruled
    /// 2026-10-03) and the folder it adds must come in that way. If the choice
    /// stopped at the screen, an Index folder would be linked and never kept in
    /// step, or a Copy would leave the project pointing at files the person then
    /// deletes. Index must reach the engine as `index`, not fall back to link.
    @Test("the way chosen in setup is the mode the folder ingest is sent", arguments: [
        (IngestMode.index, "index"), (IngestMode.copy, "copy"), (IngestMode.move, "move")
    ])
    func wayInReachesTheIngestCall(mode: IngestMode, sent: String) async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("setup-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let saved = FolderAccessManager.shared.engineAccessService
        FolderAccessManager.shared.engineAccessService = AcceptingEngine()
        defer {
            FolderAccessManager.shared.engineAccessService = saved
            try? FileManager.default.removeItem(at: folder)
        }
        let client = makeClient { request in
            if request.url?.path == "/api/ingest/folder" {
                return (200, #"{"task_id":"t1","status":"pending","path":"\#(folder.path)"}"#)
            }
            return (200, #"{"task_id":"t1","status":"completed","path":"\#(folder.path)","progress":1,"#
                    + #""total":2,"processed":2,"document_ids":["d1","d2"]}"#)
        }
        let store = RecipeSetupStore(client: client)
        store.ingestMode = mode

        await store.addFolder(folder, importer: ImportService(ficheroClient: client))

        let ingest = try #require(SetupFlowURLProtocol.seen.first { $0.path == "/api/ingest/folder" })
        #expect(ingest.body["mode"] as? String == sent)
        #expect(ingest.body["copy_mode"] as? Bool == (mode == .copy))
        #expect(store.materialAdded?.contains("2 added") == true, "the person is told what came in")
        #expect(store.errorMessage == nil)
    }

    /// WHY: the choice is asked once per project, so it is saved with the
    /// answers and read back the same. Index saved as anything but `index`, or
    /// not read back, would reopen setup on Link and the next folder would come
    /// in the wrong way.
    @Test("Index is saved as the engine's `index` and read back as Index")
    func indexRoundTrips() async throws {
        let store = RecipeSetupStore(client: makeClient { request in
            request.httpMethod == "GET"
                ? (200, #"{"answers":{"ingest_mode":"index"},"recipe":null}"#)
                : (200, #"{"answers":{},"recipe":null}"#)
        })
        store.ingestMode = .index
        #expect(await store.save())
        let answers = try #require(SetupFlowURLProtocol.seen.last?.body["answers"] as? [String: Any])
        #expect(answers["ingest_mode"] as? String == "index")

        store.ingestMode = .link
        await store.loadSaved()
        #expect(store.ingestMode == .index)
        #expect(store.errorMessage == nil)
    }
}
