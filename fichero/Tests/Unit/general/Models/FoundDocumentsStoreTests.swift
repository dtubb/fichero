//
//  FoundDocumentsStoreTests.swift
//  FicheroTests
//
//  Find the Documents in the app (#5550): a folder's Inspector lists the proposed documents still
//  waiting for a person, with Accept, Reject and Accept All Above. Written from
//  `finddocs.accept-makes-groups` and the spec's Surfaces ("the Inspector shows a proposal's evidence
//  and confidence; Accept, Reject, Accept All Above a Confidence"), not from the code.
//
//  Through the real `FoundDocumentsStore` over the generated client; only the transport is stubbed,
//  with responses shaped as `/api/find-documents/proposals` answers.
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
        request.url?.path.hasPrefix("/api/find-documents") ?? false
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

    private var posts: [FoundDocumentsURLProtocol.Seen] { FoundDocumentsURLProtocol.seen.filter { $0.method == "POST" } }

    private static func document(_ index: Int, _ name: String, first: Int, confidence: Double, state: String) -> String {
        #"{"index":\#(index),"name":"\#(name)","page_ids":["p\#(first)"],"first_position":\#(first),"#
            + #""last_position":\#(first),"confidence":\#(confidence),"state":"\#(state)","reasons":["a cue"]}"#
    }

    private static func list(_ proposals: [(String, [String])]) -> String {
        let items = proposals.map { #"{"id":"\#($0.0)","page_ids":[],"documents":[\#($0.1.joined(separator: ","))]}"# }
        return #"{"items":[\#(items.joined(separator: ","))],"count":\#(proposals.count)}"#
    }

    private static let acceptResult =
        #"{"proposal":{"id":"x","page_ids":[]},"accepted":[],"groups_made":[],"audit_id":"a1"}"#

    /// WHY: the section is the person's to-do list. A document already accepted or rejected is
    /// answered and must not be offered again, and the list reads in page order across proposals.
    @Test("Only documents still proposed are listed, in page order, for that folder")
    func listsOnlyWaitingDocumentsInPageOrder() async {
        let client = makeClient { _ in
            (200, Self.list([
                ("p2", [Self.document(0, "Later", first: 9, confidence: 0.7, state: "proposed")]),
                ("p1", [Self.document(0, "Accepted", first: 0, confidence: 0.99, state: "accepted"),
                        Self.document(1, "Earlier", first: 3, confidence: 0.6, state: "proposed"),
                        Self.document(2, "Rejected", first: 5, confidence: 0.5, state: "rejected")]),
            ]))
        }
        let store = FoundDocumentsStore(client: client)
        await store.load(folderId: "folder-1")

        #expect(store.waiting["folder-1"]?.map(\.document.name) == ["Earlier", "Later"])
        #expect(FoundDocumentsURLProtocol.seen.first?.query == "folder_id=folder-1")
    }

    /// WHY: Accept answers ONE proposed document; sending the whole proposal would group documents
    /// the person never looked at.
    @Test("Accept sends that document's index to its proposal, then reads the folder again")
    func acceptSendsTheOneDocument() async throws {
        var accepted = false
        let client = makeClient { request in
            if request.httpMethod == "POST" { accepted = true; return (200, Self.acceptResult) }
            let state = accepted ? "accepted" : "proposed"
            return (200, Self.list([("p1", [Self.document(4, "Carta", first: 2, confidence: 0.8, state: state)])]))
        }
        let store = FoundDocumentsStore(client: client)
        await store.load(folderId: "f")
        let item = try #require(store.waiting["f"]?.first)

        await store.accept(item, folderId: "f")

        #expect(posts.map(\.path) == ["/api/find-documents/proposals/p1/accept"])
        #expect(posts.first?.body["document_indexes"] as? [Int] == [4])
        #expect(store.waiting["f"]?.isEmpty == true)
    }

    @Test("Reject sends that document's index to its proposal's reject")
    func rejectSendsTheOneDocument() async throws {
        let client = makeClient { request in
            if request.httpMethod == "POST" { return (200, #"{"id":"p1","page_ids":[]}"#) }
            return (200, Self.list([("p1", [Self.document(2, "Poder", first: 0, confidence: 0.4, state: "proposed")])]))
        }
        let store = FoundDocumentsStore(client: client)
        await store.load(folderId: "f")
        let item = try #require(store.waiting["f"]?.first)

        await store.reject(item, folderId: "f")

        #expect(posts.map(\.path) == ["/api/find-documents/proposals/p1/reject"])
        #expect(posts.first?.body["document_indexes"] as? [Int] == [2])
    }

    /// WHY: Accept All Above is the engine's threshold, applied by the engine: the app sends the
    /// confidence, and only to proposals that hold something that sure.
    @Test("Accept All Above sends the threshold to each proposal holding a document that sure, and only those")
    func acceptAllAboveSendsTheThreshold() async {
        let client = makeClient { request in
            if request.httpMethod == "POST" { return (200, Self.acceptResult) }
            return (200, Self.list([
                ("p1", [Self.document(0, "Sure", first: 0, confidence: 0.93, state: "proposed")]),
                ("p2", [Self.document(0, "Unsure", first: 4, confidence: 0.5, state: "proposed")]),
            ]))
        }
        let store = FoundDocumentsStore(client: client)
        await store.load(folderId: "f")

        await store.acceptAll(above: 0.9, folderId: "f")

        #expect(posts.map(\.path) == ["/api/find-documents/proposals/p1/accept"])
        #expect(posts.first?.body["min_confidence"] as? Double == 0.9)
        #expect(posts.first?.body["document_indexes"] == nil)
    }

    /// WHY: a refusal the person never sees reads as success. The re-read after a change must not
    /// wipe the message.
    @Test("A refused accept is said, even after the folder is read again")
    func aRefusalIsShown() async throws {
        let client = makeClient { request in
            if request.httpMethod == "POST" { return (422, #"{"detail":"no"}"#) }
            return (200, Self.list([("p1", [Self.document(0, "Carta", first: 0, confidence: 0.8, state: "proposed")])]))
        }
        let store = FoundDocumentsStore(client: client)
        await store.load(folderId: "f")
        let item = try #require(store.waiting["f"]?.first)

        await store.accept(item, folderId: "f")

        #expect(store.errorMessage != nil)
        #expect(store.waiting["f"]?.count == 1)
    }
}
