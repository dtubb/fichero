//
//  SourceOutlineMigrationTests.swift
//  FicheroTests
//
//  #3030 — SourceOutlineView migrated off the hand-rolled APIClient.get onto the
//  generated `document_outline` operation. These lock the contract the view now
//  depends on: a 200 decodes the outline rows, and a non-`.ok` response THROWS
//  rather than surfacing an empty tree (prefer-raise-over-silent-fallback).
//  Reuses `MockURLProtocol` from StorageServiceGeneratedTests (same test target).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
struct SourceOutlineMigrationTests {

    private func makeClient(
        handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> FicheroClient {
        MockURLProtocol.requestHandler = handler
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: configuration)
        return FicheroClient(
            baseURL: URL(string: "https://test.fichero")!,
            libraryPath: "/tmp/test.fichero",
            session: session
        )
    }

    @Test("document_outline 200 decodes rows in preorder with counts")
    func outlineDecodesRows() async throws {
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
