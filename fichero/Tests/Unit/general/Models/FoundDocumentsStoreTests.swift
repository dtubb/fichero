//
//  FoundDocumentsStoreTests.swift
//  FicheroTests
//
//  Find the Documents in the app (#5550): the documents still proposed in a folder, and the person's answers to
//  them. Written from `finddocs.accept-makes-groups`, `finddocs.adjust` and `finddocs.review.items` ("each is the
//  engine's audited action … and one answer, even over several proposals, is one ⌘Z step"), not from the code.
//
//  Through the real `FoundDocumentsStore` over the generated client; only the transport is stubbed, with responses
//  shaped as `/api/find-documents/proposals` and `/api/actions/invoke` answer.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class FoundDocumentsURLProtocol: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) -> (Int, String))?
    struct Seen { let method: String; let path: String; let query: String; let body: [String: Any] }
    nonisolated(unsafe) static var seen: [Seen] = []

    override static func canInit(with request: URLRequest) -> Bool {
        let path = request.url?.path ?? ""
        return path.hasPrefix("/api/find-documents") || path.hasPrefix("/api/actions")
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let body = (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
        Self.seen.append(Seen(method: request.httpMethod ?? "GET", path: request.url?.path ?? "",
                              query: request.url?.query ?? "", body: body))
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
struct FoundDocumentsStoreTests {

    private func makeClient(_ handler: @escaping (URLRequest) -> (Int, String)) -> FicheroClient {
        FoundDocumentsURLProtocol.handler = handler
        FoundDocumentsURLProtocol.seen = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [FoundDocumentsURLProtocol.self]
        return FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/test.fichero",
                             session: URLSession(configuration: configuration))
    }

    /// The actions invoked, in order: (name, params).
    private var invoked: [(name: String, params: [String: Any])] {
        FoundDocumentsURLProtocol.seen.filter { $0.path == "/api/actions/invoke" }.map {
            ($0.body["name"] as? String ?? "", $0.body["params"] as? [String: Any] ?? [:])
        }
    }

    private static func document(_ index: Int, _ name: String, first: Int, confidence: Double, state: String,
                                 pages: [String]? = nil) -> String {
        let ids = (pages ?? ["p\(first)"]).map { "\"\($0)\"" }.joined(separator: ",")
        let last = first + (pages?.count ?? 1) - 1
        return #"{"index":\#(index),"name":"\#(name)","page_ids":[\#(ids)],"first_position":\#(first),"#
            + #""last_position":\#(last),"confidence":\#(confidence),"state":"\#(state)","reasons":["a cue"]}"#
    }

    private static func list(_ proposals: [(String, [String])]) -> String {
        let items = proposals.map { #"{"id":"\#($0.0)","page_ids":[],"documents":[\#($0.1.joined(separator: ","))]}"# }
        return #"{"items":[\#(items.joined(separator: ","))],"count":\#(proposals.count)}"#
    }

    nonisolated(unsafe) private static var auditCount = 0
    /// `POST /api/actions/invoke`'s answer, a fresh audit row each time.
    nonisolated private static func invokeResult() -> String {
        auditCount += 1
        return #"{"ok":true,"audit_id":"audit-\#(auditCount)","changed_domains":["document"],"result":{}}"#
    }

    /// Answers the folder's listing with `listing()`, and every action with a fresh audit row.
    private func engine(listing: @escaping () -> String) -> FicheroClient {
        makeClient { request in
            if request.url?.path == "/api/actions/invoke" { return (200, Self.invokeResult()) }
            if request.url?.path == "/api/actions/audit/undo" { 
                return (200, #"{"ok":true,"audit_ids":["inverse-1"],"results":[],"changed_domains":["document"]}"#)
            }
            return (200, listing())
        }
    }

    /// WHY: the section is the person's to-do list. A document already accepted or rejected is
    /// answered and must not be offered again, and the list reads in page order across proposals.
    @Test("Only documents still proposed are listed, in page order, for that folder")
    func listsOnlyWaitingDocumentsInPageOrder() async {
        let client = makeClient { _ in
            (200, Self.list([
                ("p2", [Self.document(0, "Later", first: 9, confidence: 0.7, state: "proposed")]),
                ("p1", [Self.document(0, "Accepted", first: 0, confidence: 0.99, state: "accepted"),
                        Self.document(1, "Earlier", first: 3, confidence: 0.6, state: "proposed"),
                        Self.document(2, "Rejected", first: 5, confidence: 0.5, state: "rejected")])
            ]))
        }
        let store = FoundDocumentsStore(client: client)
        await store.load(folderId: "folder-1")

        #expect(store.waiting["folder-1"]?.map(\.document.name) == ["Earlier", "Later"])
        #expect(FoundDocumentsURLProtocol.seen.first?.query == "folder_id=folder-1")
    }

    /// WHY: Move Page and Join act on a neighbour; one already answered cannot take a page, so the menu offers
    /// them only when the neighbour is still proposed.
    @Test("Each waiting document knows whether its neighbours are still proposed")
    func neighboursAreKnown() async {
        let client = makeClient { _ in
            (200, Self.list([("p1", [
                Self.document(0, "A", first: 0, confidence: 0.6, state: "accepted"),
                Self.document(1, "B", first: 1, confidence: 0.6, state: "proposed"),
                Self.document(2, "C", first: 2, confidence: 0.6, state: "proposed")
            ])]))
        }
        let store = FoundDocumentsStore(client: client)
        await store.load(folderId: "f")
        let waiting = store.waiting["f"] ?? []
        #expect(waiting.map(\.previousIsOpen) == [false, true])
        #expect(waiting.map(\.nextIsOpen) == [true, false])
    }

    /// WHY: Accept answers the documents the person chose and nothing more, and it must be the AUDITED action so
    /// ⌘Z takes it back: calling the route directly left no step on the window's stack.
    @Test("Accept is the audited finddocs.accept for those documents, one ⌘Z step, then the folder is read again")
    func acceptIsTheAuditedAction() async throws {
        var accepted = false
        let client = makeClient { request in
            if request.url?.path == "/api/actions/invoke" { accepted = true; return (200, Self.invokeResult()) }
            let state = accepted ? "accepted" : "proposed"
            return (200, Self.list([("p1", [Self.document(4, "Carta", first: 2, confidence: 0.8, state: state)])]))
        }
        let store = FoundDocumentsStore(client: client)
        await store.load(folderId: "f")
        let item = try #require(store.waiting["f"]?.first)
        let steps = WindowSteps()
        var reread = 0

        await store.accept([item], folderId: "f", via: .init(actions: ActionsService(client: client), steps: steps,
                                                             afterChange: { reread += 1 }))

        #expect(invoked.map(\.name) == ["finddocs.accept"])
        #expect(invoked.first?.params["proposal_id"] as? String == "p1")
        #expect(invoked.first?.params["document_indexes"] as? [Int] == [4])
        #expect(!FoundDocumentsURLProtocol.seen.contains { $0.path.hasSuffix("/accept") }, "never the bare route")
        #expect(steps.canUndo && steps.undoName == "Accept Document")
        #expect(store.waiting["f"]?.isEmpty == true, "read again")
        #expect(reread == 1, "the folder's contents are read again: an accept makes group nodes")
    }

    /// WHY (`finddocs.review.items`): "all at once" over two proposals is still one answer, so one ⌘Z takes back
    /// both; two steps would leave half the answer behind.
    @Test("Accepting documents of two proposals is one call per proposal and one step")
    func acceptAcrossProposalsIsOneStep() async throws {
        let client = engine {
            Self.list([
                ("p1", [Self.document(0, "A", first: 0, confidence: 0.6, state: "proposed"),
                        Self.document(1, "B", first: 1, confidence: 0.6, state: "proposed")]),
                ("p2", [Self.document(0, "C", first: 5, confidence: 0.6, state: "proposed")])
            ])
        }
        let store = FoundDocumentsStore(client: client)
        await store.load(folderId: "f")
        let steps = WindowSteps()
        steps.engineForProject = { _ in nil }  // the step's own service, never an open project's

        await store.accept(store.waiting["f"] ?? [], folderId: "f",
                           via: .init(actions: ActionsService(client: client), steps: steps))

        #expect(invoked.map(\.name) == ["finddocs.accept", "finddocs.accept"])
        #expect(invoked.map { $0.params["proposal_id"] as? String } == ["p1", "p2"])
        #expect(invoked.first?.params["document_indexes"] as? [Int] == [0, 1])
        #expect(steps.undoName == "Accept 3 Documents")

        steps.undo()
        // Bounded at 10 s: under the full suite the undo landed after a 2 s bound had run out.
        for _ in 0..<500 where !FoundDocumentsURLProtocol.seen.contains(where: { $0.path == "/api/actions/audit/undo" }) {
            try await Task.sleep(for: .milliseconds(20))
        }
        let undo = try #require(FoundDocumentsURLProtocol.seen.last { $0.path == "/api/actions/audit/undo" })
        #expect((undo.body["audit_ids"] as? [String])?.count == 2, "one undo takes both rows back together")
    }

    @Test("Reject is the audited finddocs.reject for that document")
    func rejectIsTheAuditedAction() async throws {
        let client = engine { Self.list([("p1", [Self.document(2, "Poder", first: 0, confidence: 0.4, state: "proposed")])]) }
        let store = FoundDocumentsStore(client: client)
        await store.load(folderId: "f")
        let item = try #require(store.waiting["f"]?.first)
        let steps = WindowSteps()

        await store.reject([item], folderId: "f", via: .init(actions: ActionsService(client: client), steps: steps))

        #expect(invoked.map(\.name) == ["finddocs.reject"])
        #expect(invoked.first?.params["document_indexes"] as? [Int] == [2])
        #expect(steps.undoName == "Reject Document")
    }

    /// WHY: Accept All Above is the engine's threshold, applied by the engine: the app sends the
    /// confidence, and only to proposals that hold something that sure.
    @Test("Accept All Above sends the threshold to each proposal holding a document that sure, and only those")
    func acceptAllAboveSendsTheThreshold() async {
        let client = engine {
            Self.list([
                ("p1", [Self.document(0, "Sure", first: 0, confidence: 0.93, state: "proposed")]),
                ("p2", [Self.document(0, "Unsure", first: 4, confidence: 0.5, state: "proposed")])
            ])
        }
        let store = FoundDocumentsStore(client: client)
        await store.load(folderId: "f")

        await store.acceptAll(above: 0.9, folderId: "f", via: .init(actions: ActionsService(client: client), steps: nil))

        #expect(invoked.map(\.name) == ["finddocs.accept"])
        #expect(invoked.first?.params["proposal_id"] as? String == "p1")
        #expect(invoked.first?.params["min_confidence"] as? Double == 0.9)
        #expect(invoked.first?.params["document_indexes"] == nil)
    }

    /// WHY (`finddocs.adjust`): which pages belong is changed by the engine's own adjustments, each named on the
    /// stack so ⌘Z says what it takes back.
    @Test("Split, Join and Move Page are the audited adjustments, each one named step")
    func adjustmentsAreTheAuditedActions() async throws {
        let client = engine {
            Self.list([("p1", [Self.document(0, "A", first: 0, confidence: 0.6, state: "proposed", pages: ["a", "b"]),
                               Self.document(1, "B", first: 2, confidence: 0.6, state: "proposed", pages: ["c"])])])
        }
        let store = FoundDocumentsStore(client: client)
        await store.load(folderId: "f")
        let first = try #require(store.waiting["f"]?.first)
        let steps = WindowSteps()
        let answering = FoundDocumentsStore.Answering(actions: ActionsService(client: client), steps: steps)

        await store.split(first, at: "b", folderId: "f", via: answering)
        #expect(steps.undoName == "Split Document")
        await store.join(first, folderId: "f", via: answering)
        #expect(steps.undoName == "Join Documents")
        await store.movePage(first, to: .next, folderId: "f", via: answering)
        #expect(steps.undoName == "Move Page to Next Document")

        #expect(invoked.map(\.name) == ["finddocs.split", "finddocs.join", "finddocs.move_page"])
        #expect(invoked[0].params["page_id"] as? String == "b")
        #expect(invoked[0].params["document_index"] as? Int == 0)
        #expect(invoked[1].params["proposal_id"] as? String == "p1")
        #expect(invoked[2].params["to"] as? String == "next")
    }

    /// WHY: a refusal the person never sees reads as success, and it must be the engine's sentence, not a code.
    /// The re-read after a change must not wipe it.
    @Test("A refused accept is said in the engine's words, even after the folder is read again")
    func aRefusalIsShown() async throws {
        let refusal = "document 1 ('Carta') is already accepted; undo that first to adjust it"
        let client = makeClient { request in
            if request.url?.path == "/api/actions/invoke" { return (409, #"{"detail":"\#(refusal)"}"#) }
            return (200, Self.list([("p1", [Self.document(0, "Carta", first: 0, confidence: 0.8, state: "proposed")])]))
        }
        let store = FoundDocumentsStore(client: client)
        await store.load(folderId: "f")
        let item = try #require(store.waiting["f"]?.first)
        let steps = WindowSteps()

        await store.accept([item], folderId: "f", via: .init(actions: ActionsService(client: client), steps: steps))

        #expect(store.errorMessage == refusal)
        #expect(store.waiting["f"]?.count == 1)
        #expect(!steps.canUndo, "a refused answer leaves no step")
    }
}
