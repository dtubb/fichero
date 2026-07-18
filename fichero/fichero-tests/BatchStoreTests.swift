@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
@Suite("BatchStore")
struct BatchStoreTests {

    private func makeStore(
        handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> BatchStore {
        MockURLProtocol.requestHandler = handler
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://test.fichero")!,
            libraryPath: "/tmp/test.fichero",
            session: URLSession(configuration: configuration)
        )
        return BatchStore(batchService: BatchService(ficheroClient: client))
    }

    private func response(for request: URLRequest, statusCode: Int = 200, body: Data) -> (HTTPURLResponse, Data) {
        (
            HTTPURLResponse(
                url: request.url!, statusCode: statusCode, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!,
            body
        )
    }

    private var batchJSON: Data {
        Data(
            """
            {"batch_id":"batch-1","workflow_id":"workflow-1","status":"pending",
             "total_items":2,"completed_items":0,"failed_items":0,"max_concurrent":5,
             "created_at":"2026-01-01T00:00:00Z"}
            """.utf8
        )
    }

    @Test("load publishes fetched batches and clears prior errors")
    func loadPublishesBatches() async {
        let store = makeStore { request in
            #expect(request.url?.path == "/api/batches")
            return response(for: request, body: Data("{\"items\":[".utf8) + batchJSON + Data("]}".utf8))
        }

        await store.load()

        #expect(store.batches.map(\.batchId) == ["batch-1"])
        #expect(store.lastError == nil)
        #expect(!store.isLoading)
    }

    @Test("runFolderBatch creates one selected-document item per folder, executes, then refreshes")
    func runFolderBatchSequencesCreateExecuteAndLoad() async {
        let store = makeStore { request in
            switch (request.httpMethod, request.url?.path) {
            case ("POST", "/api/batches"):
                let body = try #require(request.httpBody)
                let json = try #require(JSONSerialization.jsonObject(with: body) as? [String: Any])
                let items = try #require(json["items"] as? [[String: [String]]])
                #expect(items == [
                    ["selected_doc_ids": ["a", "b"]],
                    ["selected_doc_ids": ["c"]]
                ])
                return response(for: request, body: batchJSON)
            case ("POST", "/api/batches/batch-1/execute"):
                return response(for: request, body: Data())
            case ("GET", "/api/batches"):
                return response(for: request, body: Data("{\"items\":[".utf8) + batchJSON + Data("]}".utf8))
            default:
                throw URLError(.badURL)
            }
        }

        let batch = await store.runFolderBatch(
            workflowId: "workflow-1",
            folders: [(id: "folder-a", documentIds: ["a", "b"]), (id: "folder-b", documentIds: ["c"])]
        )

        #expect(batch?.batchId == "batch-1")
        #expect(store.batches.map(\.batchId) == ["batch-1"])
        #expect(store.lastError == nil)
    }

    @Test("a failed load leaves the cache intact and exposes an error")
    func loadFailureExposesError() async {
        let store = makeStore { request in
            response(for: request, statusCode: 422, body: Data(#"{"detail":[]}"#.utf8))
        }

        await store.load()

        #expect(store.batches.isEmpty)
        #expect(store.lastError != nil)
        #expect(!store.isLoading)
    }
}
