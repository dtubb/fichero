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

/// Stub URLProtocol that returns canned responses for generated client calls.
final class MockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override static func canInit(with request: URLRequest) -> Bool { true }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = MockURLProtocol.requestHandler else {
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
struct StorageServiceTests {

    private func makeService(
        baseURL: URL,
        handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> StorageService {
        MockURLProtocol.requestHandler = handler
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(baseURL: baseURL, libraryPath: "/tmp/test.fichero", session: session)
        return StorageService(ficheroClient: client)
    }

    @Test("thumbnail request maps to storage thumbnail path and returns image bytes")
    func thumbnailRequestResponseMapping() async throws {
        let baseURL = URL(string: "https://test.fichero")!
        let expectedData = Data("jpeg-bytes".utf8)
        let service = makeService(baseURL: baseURL) { request in
            #expect(request.url?.path == "/storage/thumbnail/doc-123")
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
            #expect(url.path == "/storage/thumbnail/doc-123")
        } catch {
            Issue.record("unexpected error: \(error)")
        }
    }

    @Test("source-file request maps to storage source path and returns file bytes")
    func sourceFileRequestResponseMapping() async throws {
        let baseURL = URL(string: "https://test.fichero")!
        let expectedData = Data("pdf-bytes".utf8)
        let service = makeService(baseURL: baseURL) { request in
            #expect(request.url?.path == "/storage/source/doc-456")
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

        #expect(thumbnail.path == "/storage/thumbnail/doc-abc")
        #expect(display.path == "/storage/display/doc-abc")
        #expect(source.path == "/storage/source/doc-abc")
    }
}
