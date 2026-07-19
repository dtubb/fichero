//
//  StorageServiceTests.swift
//  FicheroTests
//
//  Request/response mapping tests for StorageService using the
//  generated FicheroAPIClient and a stubbed URLProtocol.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Stub URLProtocol that returns canned responses for StorageService's generated client calls.
/// Scoped to the `/api/storage` route family (StorageService's baseURL already includes `/api`,
/// so requests land at `/api/storage/...`) so it never intercepts requests meant for other
/// test suites' dedicated protocols under Swift Testing's parallel execution.
private final class StorageMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override static func canInit(with request: URLRequest) -> Bool {
        request.url?.path.hasPrefix("/api/storage") == true
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = StorageMockURLProtocol.requestHandler else {
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
@Suite("StorageService", .serialized)
struct StorageServiceTests {

    private func makeService(
        baseURL: URL,
        handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> StorageService {
        StorageMockURLProtocol.requestHandler = handler
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StorageMockURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(baseURL: baseURL, libraryPath: "/tmp/test.fichero", session: session)
        return StorageService(ficheroClient: client)
    }

    @Test("thumbnail request maps to storage thumbnail path and returns image bytes")
    func thumbnailRequestResponseMapping() async throws {
        defer { StorageMockURLProtocol.requestHandler = nil }
        let baseURL = URL(string: "https://test.fichero")!
        let expectedData = Data("jpeg-bytes".utf8)
        let service = makeService(baseURL: baseURL) { request in
            #expect(request.url?.path == "/api/storage/thumbnail/doc-123")
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "image/jpeg"]
            )!
            return (response, expectedData)
        }

        let data = try await service.thumbnailData(for: "doc-123")
        #expect(data == expectedData)
    }

    @Test("thumbnail 404 maps to StorageServiceError.notFound")
    func thumbnailNotFoundMapping() async throws {
        defer { StorageMockURLProtocol.requestHandler = nil }
        let baseURL = URL(string: "https://test.fichero")!
        let service = makeService(baseURL: baseURL) { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 404,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data("{\"detail\":\"not found\"}".utf8))
        }

        do {
            try await service.thumbnailData(for: "doc-123")
            Issue.record("expected StorageServiceError.notFound")
        } catch StorageServiceError.notFound(let url, _) {
            #expect(url.path == "/api/storage/thumbnail/doc-123")
        } catch {
            Issue.record("unexpected error: \(error)")
        }
    }

    @Test("source-file request maps to storage source path and returns file bytes")
    func sourceFileRequestResponseMapping() async throws {
        defer { StorageMockURLProtocol.requestHandler = nil }
        let baseURL = URL(string: "https://test.fichero")!
        let expectedData = Data("pdf-bytes".utf8)
        let service = makeService(baseURL: baseURL) { request in
            #expect(request.url?.path == "/api/storage/source/doc-456")
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/pdf"]
            )!
            return (response, expectedData)
        }

        let data = try await service.getSourceData("doc-456")
        #expect(data == expectedData)
    }

    @Test("URL providers produce the expected storage paths")
    func urlProviders() {
        let service = StorageService(ficheroClient: FicheroClient(libraryPath: nil))
        let thumbnail = service.thumbnailURL(for: "doc-abc")
        let display = service.displayURL(for: "doc-abc")
        let source = service.sourceURL(for: "doc-abc")

        #expect(thumbnail.path == "/api/storage/thumbnail/doc-abc")
        #expect(display.path == "/api/storage/display/doc-abc")
        #expect(source.path == "/api/storage/source/doc-abc")
    }
}
