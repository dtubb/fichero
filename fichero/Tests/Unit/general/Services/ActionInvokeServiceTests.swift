//
//  ActionInvokeServiceTests.swift
//  FicheroTests
//
//  Request/response mapping tests for the audited-action invoke seam
//  (`invokeAction` / `undoAction`) after the #3029 migration off raw
//  URLSession onto the generated FicheroAPIClient. Uses a stubbed
//  URLProtocol so no engine is required.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// File-local URLProtocol stub for the action-invoke seam tests. A dedicated
/// class — not the shared `MockURLProtocol` — so its static handler can never
/// collide with another suite running in parallel (#4024). Scoped to the
/// `/api/actions` routes this suite mocks (invoke + undo).
private final class ActionInvokeMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override static func canInit(with request: URLRequest) -> Bool {
        request.url?.path.contains("/api/actions") == true
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = ActionInvokeMockURLProtocol.requestHandler else {
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
@Suite(.serialized)
struct ActionInvokeServiceTests {

    private func makeService(
        baseURL: URL = URL(string: "https://test.fichero")!,
        handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> ActionLibraryService {
        ActionInvokeMockURLProtocol.requestHandler = handler
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ActionInvokeMockURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(baseURL: baseURL, libraryPath: "/tmp/test.fichero", session: session)
        return ActionLibraryService(client: client)
    }

    private func okResult(auditId: String = "audit-1", domains: [String] = ["entity"]) -> Data {
        Data("""
        {"ok":true,"result":{},"audit_id":"\(auditId)","changed_domains":\(
            "[" + domains.map { "\"\($0)\"" }.joined(separator: ",") + "]"
        )}
        """.utf8)
    }

    @Test("invokeAction POSTs /api/actions/invoke with origin-window + library headers, maps result")
    func invokeMapsRequestAndResponse() async throws {
        defer { ActionInvokeMockURLProtocol.requestHandler = nil }
        let service = makeService { request in
            #expect(request.url?.path == "/api/actions/invoke")
            #expect(request.httpMethod == "POST")
            #expect(request.value(forHTTPHeaderField: "X-Fichero-Origin-Window") == "win-7")
            // Library path injected centrally by the generated middleware
            // (the whole point of migrating off the hand-built request — #3029).
            #expect(request.value(forHTTPHeaderField: "X-Fichero-Library-Path") == "/tmp/test.fichero")

            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, self.okResult(auditId: "audit-99", domains: ["acl", "user"]))
        }

        let result = try await service.invokeAction(
            name: "acl.set",
            params: AclSetParams(user: "u-1", role: "editor"),
            originWindow: "win-7"
        )
        #expect(result.succeeded == true)
        #expect(result.auditId == "audit-99")
        #expect(result.changedDomains == ["acl", "user"])
    }

    @Test("invokeAction 422 surfaces the FastAPI detail as APIError.httpError")
    func invoke422SurfacesDetail() async throws {
        defer { ActionInvokeMockURLProtocol.requestHandler = nil }
        let service = makeService { request in
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 422, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data(#"{"detail":[{"loc":["body"],"msg":"bad params","type":"value_error"}]}"#.utf8))
        }

        await #expect(throws: APIError.self) {
            try await service.invokeAction(name: "entity.merge", params: AclSetParams(user: "x"))
        }
    }

    @Test("undoAction POSTs /api/actions/audit/{id}/undo and maps the inverse result")
    func undoMapsRequestAndResponse() async throws {
        defer { ActionInvokeMockURLProtocol.requestHandler = nil }
        let service = makeService { request in
            #expect(request.url?.path == "/api/actions/audit/audit-42/undo")
            #expect(request.httpMethod == "POST")
            #expect(request.value(forHTTPHeaderField: "X-Fichero-Origin-Window") == "win-3")
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, self.okResult(auditId: "inverse-1", domains: ["entity"]))
        }

        let result = try await service.undoAction(auditId: "audit-42", originWindow: "win-3")
        #expect(result.auditId == "inverse-1")
        #expect(result.changedDomains == ["entity"])
    }

    @Test("paramsPayload bridges a typed Encodable into the free-form params container")
    func paramsPayloadBridge() throws {
        let payload = try ActionLibraryService.paramsPayload(
            AclSetParams(user: "u-9", role: "owner", remove: true)
        )
        #expect(payload.additionalProperties.value["user"] as? String == "u-9")
        #expect(payload.additionalProperties.value["role"] as? String == "owner")
        #expect(payload.additionalProperties.value["remove"] as? Bool == true)
    }
}
