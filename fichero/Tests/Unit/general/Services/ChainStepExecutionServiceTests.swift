//
//  ChainStepExecutionServiceTests.swift
//  FicheroTests
//
//  Step-wise (engine-owned) chain execution, 2026-08-30 — the workflow bar's
//  staged chain rides ChainService. Locks the transport contract:
//    * per-step provider_override/model_override survive the chain mapper,
//    * execute-steps 202 maps the pre-assigned thread id per step,
//    * execute-steps 404 surfaces as .stepExecutionUnavailable — the
//      feature-detect seam that sends the bar back to its client-side loop.
//  Own mock URLProtocol (per-session, never registered globally) so this
//  suite cannot intercept or race other suites' requests (#4024).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class ChainStepExecutionMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?
    override static func canInit(with request: URLRequest) -> Bool {
        request.url?.path.contains("/api/chains") == true
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        guard let handler = ChainStepExecutionMockURLProtocol.requestHandler else {
            client?.urlProtocol(self, didFailWithError: URLError(.notConnectedToInternet)); return }
        do { let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data); client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}

@MainActor
@Suite(.serialized)
struct ChainStepExecutionServiceTests {

    private func makeClient(
        handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> FicheroClient {
        ChainStepExecutionMockURLProtocol.requestHandler = handler
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ChainStepExecutionMockURLProtocol.self]
        let session = URLSession(configuration: configuration)
        return FicheroClient(
            baseURL: URL(string: "https://test.fichero")!,
            libraryPath: "/tmp/test.fichero",
            session: session
        )
    }

    private static func respond(
        _ request: URLRequest, status: Int, _ json: String
    ) -> (HTTPURLResponse, Data) {
        let response = HTTPURLResponse(
            url: request.url!, statusCode: status, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
        return (response, Data(json.utf8))
    }

    // A full chain envelope whose step carries the per-step pins.
    private static let pinnedChainJSON = """
    {"id":"c1","name":"Pinned","description":"",
     "steps":[{"id":"s1","workflow_id":"wf1","name":"Step 1",
               "input_mappings":[],"static_inputs":{},"condition":null,
               "continue_on_error":false,"timeout_seconds":300,
               "provider_override":"anthropic","model_override":"claude-opus-4-7"}],
     "entry_step":"s1","initial_inputs":{},
     "created_at":"2026-07-04T12:34:56.789012",
     "updated_at":"2026-07-05T01:02:03.456789",
     "folder_path":"/","sort_order":0}
    """

    @Test("per-step provider/model overrides survive the chain round-trip")
    func stepOverridesMap() async throws {
        defer { ChainStepExecutionMockURLProtocol.requestHandler = nil }
        let client = makeClient { request in
            Self.respond(request, status: 200, Self.pinnedChainJSON)
        }
        let response = try await client.api.getChainApiChainsChainIdGet(
            .init(path: .init(chainId: "c1"))
        )
        guard case .ok(let okResponse) = response else {
            Issue.record("expected .ok")
            return
        }
        let chain = try mapChainResponse(try okResponse.body.json)
        #expect(chain.steps.first?.providerOverride == "anthropic")
        #expect(chain.steps.first?.modelOverride == "claude-opus-4-7")
    }

    @Test("execute-steps 202 maps thread ids per step (engine-owned chain run)")
    func executeChainStepsMaps() async throws {
        defer { ChainStepExecutionMockURLProtocol.requestHandler = nil }
        let json = """
        {"execution_id":"e9","chain_id":"c1","status":"running",
         "steps":[{"step_id":"s1","workflow_id":"wf1","name":"Transcribe",
                   "thread_id":"thread-abc123",
                   "stream_url":"https://test.fichero/api/workflow-execution/stream/thread-abc123"}]}
        """
        let service = ChainService(apiClient: APIClient(client: makeClient { request in
            #expect(request.url?.path == "/api/chains/c1/execute-steps")
            return Self.respond(request, status: 202, json)
        }))
        let execution = try await service.executeChainSteps(
            chainId: "c1", inputs: ["selected_doc_ids": .array([.string("d1")])]
        )
        #expect(execution.executionId == "e9")
        #expect(execution.steps.count == 1)
        #expect(execution.steps.first?.stepId == "s1")
        #expect(execution.steps.first?.threadId == "thread-abc123")
    }

    @Test("execute-steps 404 surfaces as stepExecutionUnavailable — the feature-detect seam")
    func executeChainStepsFeatureDetect() async throws {
        defer { ChainStepExecutionMockURLProtocol.requestHandler = nil }
        // An older engine has no execute-steps route: the bar must fall back
        // to its client-side loop, never break. That decision keys on THIS
        // error case, so it is the contract under test.
        let service = ChainService(apiClient: APIClient(client: makeClient { request in
            Self.respond(request, status: 404, #"{"detail":"Not Found"}"#)
        }))
        do {
            _ = try await service.executeChainSteps(chainId: "c1")
            Issue.record("expected a throw on 404")
        } catch ChainServiceError.stepExecutionUnavailable {
            // expected
        } catch {
            Issue.record("expected .stepExecutionUnavailable, got \(error)")
        }
    }
}
