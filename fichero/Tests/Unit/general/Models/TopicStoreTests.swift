//
//  TopicStoreTests.swift
//  FicheroTests
//
//  Each topic's and each recipe job's explanation is written once, in the engine's
//  registry, and setup and the Inspector show those words (`source.onboard.topics-written-once`,
//  `source.onboard.teaches-the-method`, #5471). Through the real `TopicStore` and
//  `RecipeSetupStore` over the generated client; only the transport is stubbed, on this
//  suite's own session. The JSON below is what the engine returned for these ids on
//  2026-10-05 (`GET /api/topics`, `GET /api/recipes/jobs`), trimmed to the ids used.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class TopicsURLProtocol: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) -> (Int, String))?
    nonisolated(unsafe) static var paths: [String] = []

    override static func canInit(with request: URLRequest) -> Bool {
        let path = request.url?.path ?? ""
        return path.hasPrefix("/api/topics") || path.hasPrefix("/api/recipes")
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.paths.append(request.url?.path ?? "")
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
struct TopicStoreTests {

    private func makeClient(_ handler: @escaping (URLRequest) -> (Int, String)) -> FicheroClient {
        TopicsURLProtocol.handler = handler
        TopicsURLProtocol.paths = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [TopicsURLProtocol.self]
        return FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/test.fichero",
                             session: URLSession(configuration: configuration))
    }

    // Recorded from the engine (GET /api/topics), two of its fifty entries.
    private static let findLinesTopic = #"{"id":"find-lines","kind":"job","title":"Find lines","#
        + #""short":"Finds each line of writing and its baseline, so a line reader can read it.","#
        + #""long":"Kraken does this on your Mac for free.","example":null,"manual":null}"#
    private static let languagesTopic = #"{"id":"languages","kind":"topic","title":"Languages","#
        + #""short":"Each document is tagged with the languages it is written in, so the right models read it.","#
        + #""long":"Languages are named by standard tags and looked up in Glottolog, which also knows historical "#
        + #"languages and dialects.","example":"A page with a Latin formula inside Spanish text.","manual":null}"#
    private static let topicsJSON = #"{"items":["# + findLinesTopic + "," + languagesTopic + #"],"count":2}"#

    // Recorded from the engine (GET /api/recipes/jobs): each job names its `topic`.
    private static func job(_ id: String, _ name: String, topic: String) -> String {
        #"{"id":"\#(id)","name":"\#(name)","description":"\#(name), as the engine joins it","topic":"\#(topic)","#
            + #""layer":"lines","takes":["page_image"],"gives":["lines"],"compare":"c","settings":[],"#
            + #""since":"2026.10.03"}"#
    }
    private static let jobsJSON = #"{"count":2,"items":["#
        + job("find-lines", "Find lines", topic: "find-lines") + ","
        + job("correct", "Correct", topic: "correct") + "]}"

    private static let recipeJSON = #"{"id":"generated","title":"t","purposes":["transcribe"],"steps":["#
        + #"{"id":"lines","job":"find-lines","reasons":[]},{"id":"fix","job":"correct","reasons":[]},"#
        + #"{"id":"odd","job":"not-a-job","reasons":[]}],"gaps":[],"problems":[]}"#

    private func engine(_ request: URLRequest) -> (Int, String) {
        switch request.url?.path {
        case "/api/topics": return (200, Self.topicsJSON)
        case "/api/recipes/jobs": return (200, Self.jobsJSON)
        default: return (200, Self.recipeJSON)
        }
    }

    // MARK: source.onboard.topics-written-once

    /// WHY: setup's explanation of a step must be the registry's topic, the same words the
    /// Inspector and the manual show. If setup went on showing the job's `description` (or any
    /// text the app holds), a sentence corrected in the registry would still read the old way
    /// in setup, and the two places would drift. The project's Inspector passes the library's
    /// own TopicStore, so it must be the store setup reads, not a copy.
    @Test("a step's explanation in setup is its topic's text, from the library's TopicStore")
    func stepExplanationIsTheTopicsText() async throws {
        let client = makeClient(engine)
        let topics = TopicStore(client: client)
        let store = RecipeSetupStore(client: client, topics: topics)
        store.languages = ["es"]
        store.scripts = ["Latn"]

        await store.loadJobs()
        await store.assemble()

        #expect(store.topics === topics, "the library's one store, not a second copy")
        #expect(TopicsURLProtocol.paths.contains("/api/topics"))
        let steps = try #require(store.recipe?.steps)
        let explanation = try #require(store.explanation(ofJob: steps[0].job))
        #expect(explanation.short == "Finds each line of writing and its baseline, so a line reader can read it.")
        #expect(explanation.long == "Kraken does this on your Mac for free.")
        #expect(store.title(of: steps[0]) == "Find lines")
        #expect(explanation.short != store.job(for: steps[0])?.description, "the topic's words, not the job's description")
    }

    /// WHY: a job whose topic the registry lacks (an older engine, a typo in the registry) or a
    /// step naming a job nobody registered must still be shown, by its name, with no
    /// explanation invented in the app and no crash.
    @Test("a missing topic id shows the job's name, and an unknown job its id, without a crash")
    func missingTopicShowsTheJobName() async throws {
        let client = makeClient(engine)
        let store = RecipeSetupStore(client: client)
        store.languages = ["es"]
        store.scripts = ["Latn"]

        await store.loadJobs()
        await store.assemble()

        let steps = try #require(store.recipe?.steps)
        #expect(store.explanation(ofJob: "correct") == nil, "no topic `correct` in the registry")
        #expect(store.title(of: steps[1]) == "Correct", "the job's registered name stands alone")
        #expect(store.explanation(ofJob: "not-a-job") == nil)
        #expect(store.title(of: steps[2]) == "not-a-job", "an unknown job shows its id, never an invented name")
    }

    /// WHY: when the topics cannot be read, setup must still show each step by its job name
    /// and say why the explanations are missing, rather than showing nothing or crashing.
    @Test("an unreadable registry leaves names standing and says so")
    func unreadableRegistryLeavesNames() async throws {
        let client = makeClient { request in
            request.url?.path == "/api/topics" ? (500, "{}") : self.engine(request)
        }
        let store = RecipeSetupStore(client: client)
        store.languages = ["es"]
        store.scripts = ["Latn"]

        await store.loadJobs()
        await store.assemble()

        let steps = try #require(store.recipe?.steps)
        #expect(store.explanation(ofJob: "find-lines") == nil)
        #expect(store.title(of: steps[0]) == "Find lines")
        #expect(store.topics.topics.isEmpty)
        #expect(store.topics.errorMessage != nil, "the missing explanations are said, not silent")
    }

    // MARK: observable data layer: loaded once, one item in place

    /// WHY: the list is read once per library (every setup screen and the Inspector ask for
    /// it), and refreshing a topic replaces only that topic: a wholesale reload would redraw
    /// every explanation on screen and could drop the ones the refresh did not return.
    @Test("topics load once; a refresh replaces one topic in place")
    func loadOnceRefreshOneInPlace() async throws {
        var languages = Self.languagesTopic
        let client = makeClient { request in
            switch request.url?.path {
            case "/api/topics": return (200, Self.topicsJSON)
            case "/api/topics/languages": return (200, languages)
            default: return (404, "{}")
            }
        }
        let store = TopicStore(client: client)

        await store.load()
        await store.load()
        #expect(TopicsURLProtocol.paths.filter { $0 == "/api/topics" }.count == 1, "read once")
        #expect(store.topics.count == 2)

        languages = languages.replacingOccurrences(of: "so the right models read it", with: "so the right models read each")
        await store.refresh("languages")

        #expect(store.topic("languages")?.short.hasSuffix("so the right models read each.") == true)
        #expect(store.topic("find-lines")?.long == "Kraken does this on your Mac for free.", "the other topic untouched")
        #expect(store.topics.count == 2)
        #expect(store.topic(nil) == nil)
    }
}
