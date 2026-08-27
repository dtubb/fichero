//
//  SourceOutlineMigrationTests.swift
//  FicheroTests
//
//  #3030 — SourceOutlineView migrated off the hand-rolled APIClient.get onto the
//  generated `document_outline` operation. These lock the contract the view now
//  depends on: a 200 decodes the outline rows, and a non-`.ok` response THROWS
//  rather than surfacing an empty tree (prefer-raise-over-silent-fallback).
//
//  #4024 — This suite used to reuse the shared `MockURLProtocol` from
//  StorageServiceTests. That class's `requestHandler` is a single type-level
//  static shared by every migration-test file in the target, and every one of
//  those files' `canInit(with:)` matched ALL requests unconditionally. Under
//  Swift Testing's default parallel execution, a concurrently-running suite
//  (e.g. BatchServiceTests hitting GET /api/batches, SchedulesMigrationTests
//  hitting GET /api/schedules) could have its request intercepted by whichever
//  handler last won the race to set `MockURLProtocol.requestHandler` — here,
//  this suite's outline handler — producing spurious
//  `request.url?.path == "/api/documents/doc-1/outline"` failures and, worse,
//  hangs that SIGTERM-killed the whole run. Fix: this suite now registers its
//  OWN dedicated `OutlineMockURLProtocol` (below), scoped to `/outline` paths
//  and never shared with any other test file, plus `.serialized` so this
//  suite's own two tests can't race each other over the one static slot.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Dedicated stub URLProtocol for THIS suite only. Deliberately not the shared
/// `MockURLProtocol` (StorageServiceTests.swift) — see the file-header note.
/// Registered solely on this suite's own `URLSessionConfiguration.protocolClasses`,
/// so no other suite's `URLSession` can ever route through it. `canInit` is also
/// scoped to outline paths as defense-in-depth: even if this class were ever
/// reused elsewhere, it would refuse to answer for `/api/batches`, `/api/schedules`,
/// or any other non-outline request rather than mis-handling it.
private final class OutlineMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override static func canInit(with request: URLRequest) -> Bool {
        request.url?.path.contains("/outline") == true
    }

    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = OutlineMockURLProtocol.requestHandler else {
            client?.urlProtocol(self, didFailWithError: URLError(.notConnectedToInternet))
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

/// `.serialized`: both tests below share `OutlineMockURLProtocol.requestHandler`
/// (a type-level static). Running them one at a time — instead of relying on
/// Swift Testing's default concurrent execution — keeps that single static slot
/// deterministic within this suite, so the two tests here can never stomp on
/// each other's handler even though neither can touch any OTHER suite's.
@Suite(.serialized)
@MainActor
struct SourceOutlineMigrationTests {

    private func makeClient(
        handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> FicheroClient {
        OutlineMockURLProtocol.requestHandler = handler
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [OutlineMockURLProtocol.self]
        let session = URLSession(configuration: configuration)
        return FicheroClient(
            baseURL: URL(string: "https://test.fichero")!,
            libraryPath: "/tmp/test.fichero",
            session: session
        )
    }

    @Test("document_outline 200 decodes rows in preorder with counts")
    func outlineDecodesRows() async throws {
        defer { OutlineMockURLProtocol.requestHandler = nil }
        let client = makeClient { request in
            #expect(request.url?.path == "/api/documents/doc-1/outline")
            let json = """
            {"document_id":"doc-1","count":2,"rows":[
              {"id":"r1","depth":0,"kind":"chapter","label":"Intro","count":1},
              {"id":"r2","depth":1,"kind":"page","label":"p1","count":0}
            ]}
            """
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data(json.utf8))
        }

        let response = try await client.api.documentOutlineApiDocumentsDocumentIdOutlineGet(
            path: .init(documentId: "doc-1")
        )
        guard case .ok(let okResponse) = response else {
            Issue.record("expected .ok")
            return
        }
        let rows = try okResponse.body.json.rows
        #expect(rows.count == 2)
        #expect(rows[0].id == "r1")
        #expect(rows[0].depth == 0)
        #expect(rows[0].kind == "chapter")
        #expect(rows[1].depth == 1)
        // `count` is a numeric child-count field, not a collection.
        #expect(rows[1].count == 0)  // swiftlint:disable:this empty_count
    }

    @Test("document_outline non-ok surfaces as non-.ok (never a silent empty tree)")
    func outlineNonOkThrows() async throws {
        defer { OutlineMockURLProtocol.requestHandler = nil }
        let client = makeClient { request in
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 500, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data("{\"detail\":\"boom\"}".utf8))
        }

        let response = try await client.api.documentOutlineApiDocumentsDocumentIdOutlineGet(
            path: .init(documentId: "doc-1")
        )
        // A 500 is undocumented for this op → the view's switch throws on this
        // case instead of building an empty tree.
        if case .ok = response {
            Issue.record("500 must not decode as .ok")
        }
    }
}
