//
//  ChainServiceMigrationTests.swift
//  FicheroTests
//
//  #3030 (closes the EPIC) — ChainService migrated off the hand-rolled APIClient
//  generic get/post/put/delete onto the generated typed chain operations, with
//  inline mappers. These decode real chain envelopes through the generated client
//  and run them through those mappers, locking the bits that mattered:
//    * folder_path / sort_order survive the round-trip (the whole point of #3136),
//    * created_at/updated_at (engine `datetime.isoformat()`, microsecond, offset-
//      less) parse to Date,
//    * the free-form initial_inputs / final_outputs escape passes through,
//    * execution-status step_results default the app-only inputs/outputs/files
//      fields the backend never sends (fixes a latent legacy decode failure),
//    * a non-.ok status surfaces as non-.ok (never a silent empty chain).
//  Reuses MockURLProtocol (defined in the same test target).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
struct ChainServiceMigrationTests {

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

    private static func ok(_ request: URLRequest, _ json: String) -> (HTTPURLResponse, Data) {
        let response = HTTPURLResponse(
            url: request.url!, statusCode: 200, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
        return (response, Data(json.utf8))
    }

    // A full ChainResponse with a step, free-form initial_inputs, folder_path,
    // sort_order and engine-style (naive, microsecond) timestamps.
    private static let chainJSON = """
    {"id":"c1","name":"My Chain","description":"a chain",
     "steps":[{"id":"s1","workflow_id":"wf1","name":"Step 1",
               "input_mappings":[{"source_path":"a","target_key":"b","transform":null}],
               "static_inputs":{"k":"v"},"condition":null,
               "continue_on_error":false,"timeout_seconds":300}],
     "entry_step":"s1",
     "initial_inputs":{"greeting":"hello","count":3},
     "created_at":"2026-07-04T12:34:56.789012",
     "updated_at":"2026-07-05T01:02:03.456789",
     "folder_path":"/chains","sort_order":7}
    """

    @Test("get_chain maps folder_path/sort_order, dates, steps + free-form inputs")
    func getChainMaps() async throws {
        let client = makeClient { request in
            #expect(request.url?.path == "/api/chains/c1")
            return Self.ok(request, Self.chainJSON)
        }

        let response = try await client.api.getChainApiChainsChainIdGet(
            .init(path: .init(chainId: "c1"))
        )
        guard case .ok(let okResponse) = response else {
            Issue.record("expected .ok")
            return
        }
        let chain = try mapChainResponse(try okResponse.body.json)

        #expect(chain.id == "c1")
        #expect(chain.name == "My Chain")
        // The whole point of #3136 — these must survive the migration.
        #expect(chain.folderPath == "/chains")
        #expect(chain.sortOrder == 7)
        #expect(chain.entryStep == "s1")
        // Free-form escape passes through untouched.
        #expect(chain.initialInputs["greeting"] == .string("hello"))
        #expect(chain.initialInputs["count"] == .int(3))
        // Nested step + its own free-form static_inputs.
        #expect(chain.steps.count == 1)
        #expect(chain.steps.first?.workflowId == "wf1")
        #expect(chain.steps.first?.staticInputs["k"] == .string("v"))
        #expect(chain.steps.first?.inputMappings.first?.sourcePath == "a")
        // Engine microsecond/offset-less isoformat parses to Date.
        #expect(chain.createdAt == parseEngineDate("2026-07-04T12:34:56.789012"))
        #expect(chain.updatedAt == parseEngineDate("2026-07-05T01:02:03.456789"))
    }

    @Test("list_chains maps every item, preserving folder_path/sort_order")
    func listChainsMaps() async throws {
        let client = makeClient { request in
            #expect(request.url?.path == "/api/chains")
            let json = "{\"chains\":[\(Self.chainJSON)],\"total\":1}"
            return Self.ok(request, json)
        }

        let response = try await client.api.listChainsApiChainsGet(.init(query: .init(limit: 50)))
        guard case .ok(let okResponse) = response else {
            Issue.record("expected .ok")
            return
        }
        let chains = try okResponse.body.json.chains.map { try mapChainResponse($0) }
        #expect(chains.count == 1)
        #expect(chains.first?.folderPath == "/chains")
        #expect(chains.first?.sortOrder == 7)
    }

    // A minimal ChainResponse (all 10 required fields) parameterized by the bits
    // #3136 exposed, so a list can carry several with distinct folder_path/sort_order.
    private static func chainJSON(id: String, sortOrder: Int, folderPath: String) -> String {
        """
        {"id":"\(id)","name":"\(id)","description":"",
         "steps":[],"entry_step":"\(id)-s","initial_inputs":{},
         "created_at":"2026-07-04T12:34:56.789012",
         "updated_at":"2026-07-05T01:02:03.456789",
         "folder_path":"\(folderPath)","sort_order":\(sortOrder)}
        """
    }

    @Test("list_chains keeps each id paired with its folder_path/sort_order in server order")
    func listChainsPreservesOrderAndPairing() async throws {
        // Three chains, deliberately NOT sorted by sort_order. The mapper must keep
        // every id bound to its own folder_path/sort_order and preserve the server's
        // array order (it maps 1:1 — never resorts or drops a field per item).
        let items = [
            Self.chainJSON(id: "c-b", sortOrder: 5, folderPath: "/b"),
            Self.chainJSON(id: "c-a", sortOrder: 1, folderPath: "/a"),
            Self.chainJSON(id: "c-c", sortOrder: 9, folderPath: "/c")
        ].joined(separator: ",")
        let client = makeClient { request in
            #expect(request.url?.path == "/api/chains")
            return Self.ok(request, "{\"chains\":[\(items)],\"total\":3}")
        }

        let response = try await client.api.listChainsApiChainsGet(.init(query: .init(limit: 50)))
        guard case .ok(let okResponse) = response else {
            Issue.record("expected .ok")
            return
        }
        let chains = try okResponse.body.json.chains.map { try mapChainResponse($0) }

        #expect(chains.map(\.id) == ["c-b", "c-a", "c-c"])       // server order preserved
        #expect(chains.map(\.sortOrder) == [5, 1, 9])            // paired, not resorted
        #expect(chains.map(\.folderPath) == ["/b", "/a", "/c"])  // paired, not shifted
    }

    @Test("get_chain non-.ok surfaces as non-.ok (never a silent empty chain)")
    func getChainNonOk() async throws {
        let client = makeClient { request in
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 500, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data("{\"detail\":\"boom\"}".utf8))
        }

        let response = try await client.api.getChainApiChainsChainIdGet(
            .init(path: .init(chainId: "c1"))
        )
        if case .ok = response {
            Issue.record("500 must NOT decode as .ok — ChainService throws unexpectedResponse")
        }
    }

    @Test("execution status defaults the app-only step-result fields the backend omits")
    func executionStatusMaps() async throws {
        // Backend ChainStepResultInfo carries only id/workflow_id/status/error/
        // duration_ms — never inputs/outputs/output_files. The mapper defaults
        // those, fixing the legacy keyNotFound decode on non-empty step_results.
        let json = """
        {"execution_id":"e1","chain_id":"c1","status":"completed",
         "step_results":[{"step_id":"s1","workflow_id":"wf1","status":"completed",
                          "error":null,"duration_ms":12.5}],
         "final_outputs":{"answer":"42"},
         "final_files":["/out/a.txt"],
         "total_duration_ms":34.0,
         "events":[{"event_type":"step_completed","step_id":"s1","message":"done",
                    "progress":1.0,"timestamp":"2026-07-04T12:34:56.789012"}]}
        """
        let client = makeClient { request in
            #expect(request.url?.path == "/api/chains/executions/e1")
            return Self.ok(request, json)
        }

        let response = try await client.api.getChainExecutionApiChainsExecutionsExecutionIdGet(
            .init(path: .init(executionId: "e1"))
        )
        guard case .ok(let okResponse) = response else {
            Issue.record("expected .ok")
            return
        }
        let status = mapExecutionStatus(try okResponse.body.json)

        #expect(status.executionId == "e1")
        #expect(status.status == "completed")
        #expect(status.stepResults.count == 1)
        let step = try #require(status.stepResults.first)
        #expect(step.stepId == "s1")
        #expect(step.status == .completed)
        #expect(step.durationMs == 12.5)
        // App-only fields the backend never sends → empty, not a decode crash.
        #expect(step.inputs.isEmpty)
        #expect(step.outputs.isEmpty)
        #expect(step.outputFiles.isEmpty)
        // Free-form final_outputs escape preserved.
        #expect(status.finalOutputs["answer"] == .string("42"))
        #expect(status.finalFiles == ["/out/a.txt"])
        #expect(status.totalDurationMs == 34.0)
        #expect(status.events.first?.eventType == "step_completed")
        #expect(status.events.first?.progress == 1.0)
    }
}
