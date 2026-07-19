@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Stub URLProtocol dedicated to BatchService tests, scoped to the `/api/batches` route
/// family so it never intercepts requests meant for other suites' dedicated protocols
/// under Swift Testing's parallel execution.
private final class BatchServiceMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override static func canInit(with request: URLRequest) -> Bool {
        request.url?.path.hasPrefix("/api/batches") == true
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = BatchServiceMockURLProtocol.requestHandler else {
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

@MainActor
@Suite("BatchService", .serialized)
struct BatchServiceTests {

    private func makeService(
        handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> BatchService {
        BatchServiceMockURLProtocol.requestHandler = handler
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [BatchServiceMockURLProtocol.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://test.fichero")!,
            libraryPath: "/tmp/test.fichero",
            session: URLSession(configuration: configuration)
        )
        return BatchService(ficheroClient: client)
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

    @Test("createBatch encodes workflow and per-folder selected document ids")
    func createBatchRequest() async throws {
        defer { BatchServiceMockURLProtocol.requestHandler = nil }
        let service = makeService { request in
            #expect(request.url?.path == "/api/batches")
            #expect(request.httpMethod == "POST")
            let body = try #require(request.httpBody)
            let json = try #require(JSONSerialization.jsonObject(with: body) as? [String: Any])
            #expect(json["workflow_id"] as? String == "workflow-1")
            #expect(json["max_concurrent"] as? Int == 3)
            let items = try #require(json["items"] as? [[String: [String]]])
            #expect(items == [["selected_doc_ids": ["doc-1", "doc-2"]]])
            return response(for: request, body: batchJSON)
        }

        let batch = try await service.createBatch(
            workflowId: "workflow-1",
            items: [["selected_doc_ids": ["doc-1", "doc-2"]]],
            maxConcurrent: 3
        )

        #expect(batch.batchId == "batch-1")
        #expect(batch.totalItems == 2)
    }

    @Test("listBatches passes status and limit filters through the generated client")
    func listBatchesRequest() async throws {
        defer { BatchServiceMockURLProtocol.requestHandler = nil }
        let service = makeService { request in
            #expect(request.url?.path == "/api/batches")
            let query = URLComponents(url: try #require(request.url), resolvingAgainstBaseURL: false)?.queryItems
            #expect(query?.first { $0.name == "status" }?.value == "running")
            #expect(query?.first { $0.name == "limit" }?.value == "7")
            return response(
                for: request,
                body: Data(
                    """
                    {"items":[{"batch_id":"batch-1","workflow_id":"workflow-1","status":"pending",
                    "total_items":2,"completed_items":0,"failed_items":0,"max_concurrent":5,
                    "created_at":"2026-01-01T00:00:00Z"}]}
                    """.utf8
                )
            )
        }

        let batches = try await service.listBatches(status: "running", limit: 7)

        #expect(batches.map(\.batchId) == ["batch-1"])
    }

    @Test("executeBatch targets the batch-specific execute route")
    func executeBatchRequest() async throws {
        defer { BatchServiceMockURLProtocol.requestHandler = nil }
        let service = makeService { request in
            #expect(request.url?.path == "/api/batches/batch-1/execute")
            #expect(request.httpMethod == "POST")
            return response(for: request, body: Data())
        }

        try await service.executeBatch(batchId: "batch-1")
    }
}
