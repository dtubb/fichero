//
//  DocumentListMigrationTests.swift
//  FicheroTests
//
//  #3030 — ChatInspector's scope search + scoped-doc load migrated off the
//  hand-rolled APIClient.get onto DocumentServiceGenerated.listDocuments(limit:)
//  and .getDocument(_:). These cover the new listDocuments wrapper: it sends the
//  `limit` query param on the generated `list_documents` op and maps items into
//  local Documents; a non-.ok response throws instead of yielding an empty list.
//  Reuses `MockURLProtocol` from StorageServiceGeneratedTests (same target).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
struct DocumentListMigrationTests {

    private func makeService(
        handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> DocumentServiceGenerated {
        MockURLProtocol.requestHandler = handler
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(
            baseURL: URL(string: "https://test.fichero")!,
            libraryPath: "/tmp/test.fichero",
            session: session
        )
        return DocumentServiceGenerated(ficheroClient: client)
    }

    @Test("listDocuments sends limit query and maps items to local Documents")
    func listDocumentsMapsItems() async throws {
        let service = makeService { request in
            #expect(request.url?.path == "/api/documents")
            #expect((request.url?.query ?? "").contains("limit=100"))
            let json = """
            {"count":2,"items":[
              {"id":"d1","name":"Alpha","doc_type":"file","expected_thumbnail_path":"t1","expected_display_path":"v1"},
              {"id":"d2","name":"Beta","doc_type":"file","expected_thumbnail_path":"t2","expected_display_path":"v2"}
            ]}
            """
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data(json.utf8))
        }

        let docs = try await service.listDocuments(limit: 100)
        #expect(docs.count == 2)
        #expect(docs.map(\.id) == ["d1", "d2"])
        #expect(docs.map(\.name) == ["Alpha", "Beta"])
    }

    @Test("listDocuments() with nil limit omits the limit query (sidebar load-all)")
    func listDocumentsNilLimitOmitsParam() async throws {
        let service = makeService { request in
            #expect(request.url?.path == "/api/documents")
            // loadCollections loads the full tree — no limit cap must be sent.
            #expect(!(request.url?.query ?? "").contains("limit="))
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data("{\"count\":0,\"items\":[]}".utf8))
        }

        let docs = try await service.listDocuments()
        #expect(docs.isEmpty)
    }

    @Test("listDocuments throws on non-.ok instead of returning an empty list")
    func listDocumentsThrowsOnError() async throws {
        let service = makeService { request in
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 500, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data("{\"detail\":\"boom\"}".utf8))
        }

        await #expect(throws: (any Error).self) {
            _ = try await service.listDocuments(limit: 100)
        }
    }

    @Test("updateDocument(name:) PUTs to /api/documents/{id} (DocumentStore rename path)")
    func updateDocumentRenameContract() async throws {
        let service = makeService { request in
            #expect(request.httpMethod == "PUT")
            #expect(request.url?.path == "/api/documents/d1")
            let json = """
            {"id":"d1","name":"Renamed","doc_type":"file","expected_thumbnail_path":"t","expected_display_path":"v"}
            """
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data(json.utf8))
        }

        let doc = try await service.updateDocument("d1", name: "Renamed")
        #expect(doc.name == "Renamed")
    }

    @Test("getParent GETs /api/documents/{id}/parent (KG/source navigation)")
    func getParentContract() async throws {
        let service = makeService { request in
            #expect(request.httpMethod == "GET")
            #expect(request.url?.path == "/api/documents/child-1/parent")
            let json = """
            {"id":"parent-1","name":"Folder","doc_type":"folder","expected_thumbnail_path":"t","expected_display_path":"v"}
            """
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data(json.utf8))
        }

        let parent = try await service.getParent("child-1")
        #expect(parent.id == "parent-1")
    }

    @Test("deleteDocument DELETEs /api/documents/{id} (DocumentStore delete path)")
    func deleteDocumentContract() async throws {
        let service = makeService { request in
            #expect(request.httpMethod == "DELETE")
            #expect(request.url?.path == "/api/documents/d9")
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 204, httpVersion: nil, headerFields: [:]
            )!
            return (response, Data())
        }

        try await service.deleteDocument("d9")
    }
}
