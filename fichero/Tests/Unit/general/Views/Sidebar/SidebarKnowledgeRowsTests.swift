//
//  SidebarKnowledgeRowsTests.swift
//  FicheroTests
//
//  sidebar-crud (#5413): `sidebar.knowledge.rows-only-when-non-empty` and
//  `sidebar.knowledge.bottom-bar-toggle`. A project's knowledge rows draw only while they hold an
//  item, live from the change stream, and one bottom-bar control hides or shows them.
//  Driven through the real `KnowledgeRowCountsStore` and the generated client against a stub
//  scoped to /api/stats/knowledge, replying with the route's shape as the engine's own
//  `test_knowledge_row_counts.py` records it (all seven keys, integers).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import SwiftUI
import Testing

private final class KnowledgeCountsMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var replies: [String] = []
    nonisolated(unsafe) static var requests = 0
    override static func canInit(with request: URLRequest) -> Bool {
        request.url?.path == "/api/stats/knowledge"
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let index = min(Self.requests, Self.replies.count - 1)
        Self.requests += 1
        let response = HTTPURLResponse(
            url: request.url!, statusCode: 200, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(Self.replies[index].utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor
@Suite(.serialized, .tags(.sidebar))
struct SidebarKnowledgeRowsTests {
    private static func counts(
        entities: Int = 0, claims: Int = 0, citations: Int = 0, references: Int = 0,
        interpretations: Int = 0, frameworks: Int = 0, patterns: Int = 0
    ) -> String {
        """
        {"entities": \(entities), "claims": \(claims), "citations": \(citations), \
        "references": \(references), "interpretations": \(interpretations), \
        "frameworks": \(frameworks), "patterns": \(patterns)}
        """
    }

    private func makeStore(replies: [String]) -> KnowledgeRowCountsStore {
        KnowledgeCountsMockURLProtocol.replies = replies
        KnowledgeCountsMockURLProtocol.requests = 0
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [KnowledgeCountsMockURLProtocol.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://test.fichero")!,
            libraryPath: "/tmp/test.fichero",
            session: URLSession(configuration: configuration)
        )
        // A long debounce: these tests flush by hand, so a scheduled read never races them.
        return KnowledgeRowCountsStore(client: client, reloadDebouncer: ReloadDebouncer(delay: .seconds(60)))
    }

    private static func event(_ type: String) throws -> ChangeEvent {
        try JSONDecoder().decode(ChangeEvent.self, from: Data(#"{"type": "\#(type)"}"#.utf8))
    }

    @Test("a row with 0 items is hidden and a row with items is shown, from the engine's counts")
    func rowsShowOnlyWhenNonEmpty() async {
        // WHY: the ruling removes empty rows; a new project must draw no knowledge rows at all,
        // and a project with claims but no entities must draw Claims alone.
        let empty = makeStore(replies: [Self.counts()])
        await empty.load()
        #expect(KnowledgeCountsMockURLProtocol.requests == 1)
        #expect(empty.nonEmptyRows.isEmpty)
        #expect(empty.errorMessage == nil)

        let some = makeStore(replies: [Self.counts(claims: 4, citations: 2)])
        await some.load()
        #expect(some.count(of: .claims) == 4)
        #expect(some.count(of: .citations) == 2)
        #expect(some.count(of: .entities) == 0)
        #expect(some.nonEmptyRows == [.claims])
        #expect(SidebarKnowledgeRows.rows(of: some, shown: true) == [.claims])
    }

    @Test("a change event for one kind re-reads the route and updates only that count, in place")
    func changeEventUpdatesThatCountInPlace() async throws {
        // WHY: a row must appear live when its first item arrives, without reloading every
        // count; an entity event must move Entities and leave the other rows as they were.
        let store = makeStore(replies: [
            Self.counts(claims: 1),
            Self.counts(entities: 1, claims: 9)
        ])
        await store.load()
        #expect(store.nonEmptyRows == [.claims])

        store.apply(try Self.event("entity.created"))
        await store.refreshPendingKinds()

        #expect(KnowledgeCountsMockURLProtocol.requests == 2)
        #expect(store.count(of: .entities) == 1)
        // The claim count was not named by the event, so it is not rewritten.
        #expect(store.count(of: .claims) == 1)
        #expect(store.nonEmptyRows == [.entities, .claims])
    }

    @Test("an event of a kind the counts do not hold asks nothing")
    func unrelatedEventAsksNothing() async throws {
        // WHY: the store hears five domains; a stray event must not cost a route read.
        let store = makeStore(replies: [Self.counts()])
        #expect(store.changeDomains == ["entity", "claim", "citation", "reference", "interpretation"])
        store.apply(try Self.event("document.updated"))
        await store.refreshPendingKinds()
        #expect(KnowledgeCountsMockURLProtocol.requests == 0)
    }

    @Test("the toggle hides and shows the rows and remembers its setting")
    func toggleHidesShowsAndPersists() async throws {
        // WHY: a person who hides the knowledge rows expects them to stay hidden next launch;
        // the setting is the same stored value the bar's control writes.
        let suite = "SidebarKnowledgeRowsTests.\(UUID().uuidString)"
        let defaults = try #require(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }

        let store = makeStore(replies: [Self.counts(entities: 3, claims: 2)])
        await store.load()

        let setting = SidebarKnowledgeRows.shownSetting(store: defaults)
        #expect(setting.wrappedValue)
        #expect(SidebarKnowledgeRows.rows(of: store, shown: setting.wrappedValue) == [.entities, .claims])

        setting.wrappedValue = false
        let relaunched = SidebarKnowledgeRows.shownSetting(store: defaults)
        #expect(!relaunched.wrappedValue)
        #expect(defaults.bool(forKey: SidebarKnowledgeRows.shownKey) == false)
        #expect(SidebarKnowledgeRows.rows(of: store, shown: relaunched.wrappedValue).isEmpty)

        relaunched.wrappedValue = true
        #expect(SidebarKnowledgeRows.shownSetting(store: defaults).wrappedValue)
        #expect(SidebarKnowledgeRows.rows(of: store, shown: true) == [.entities, .claims])
    }

    @Test("the toggle is absent when no project has a knowledge row, present when one does")
    func toggleAbsentWithoutRows() async {
        // WHY: a control with nothing to hide is chrome that does nothing; it appears with the
        // first project that has a non-empty row.
        let empty = makeStore(replies: [Self.counts(citations: 5)])
        await empty.load()
        #expect(!SidebarKnowledgeRows.toggleIsShown([]))
        // Citations has no sidebar row yet, so a count there alone draws no row and no toggle.
        #expect(!SidebarKnowledgeRows.toggleIsShown([empty]))

        let withRows = makeStore(replies: [Self.counts(entities: 2)])
        await withRows.load()
        #expect(SidebarKnowledgeRows.toggleIsShown([empty, withRows]))
    }
}
