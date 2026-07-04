//
//  TriggersMigrationTests.swift
//  FicheroTests
//
//  #3030 (post-#3131) — AutomationService trigger ops migrated onto the generated
//  typed operations. Decodes a real TriggerResponse through the generated client
//  and runs it through the TriggerInfo mapper (flat fields + typed inputs_template).
//  Reuses MockURLProtocol (same test target).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
struct TriggersMigrationTests {

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

    private static let triggerJSON = """
    {"trigger_id":"t1","name":"Watch","workflow_id":"wf1","watch_path":"/inbox",
     "recursive":true,"events":["created","modified"],"filter_mode":"glob",
     "filter_pattern":"*.pdf","filter_extensions":["pdf"],"exclude_patterns":[],
     "debounce_seconds":1.5,"batch_delay_seconds":2.0,"inputs_template":{"k":"v"},
     "status":"active","use_batch":false,"max_concurrent":1,
     "created_at":"2026-07-04T00:00:00Z","updated_at":"2026-07-04T00:00:00Z",
     "last_triggered_at":null,"trigger_count":7,"error_message":null}
    """

    @Test("list_triggers decodes + maps items into TriggerInfo (flat fields + inputs_template)")
    func listTriggersMaps() async throws {
        let client = makeClient { request in
            #expect(request.url?.path == "/api/triggers")
            let json = "{\"count\":1,\"items\":[\(Self.triggerJSON)]}"
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data(json.utf8))
        }

        let response = try await client.api.listTriggersApiTriggersGet(.init(query: .init(limit: 100)))
        guard case .ok(let okResponse) = response else {
            Issue.record("expected .ok")
            return
        }
        let triggers = try okResponse.body.json.items.map { TriggerInfo(response: $0) }
        #expect(triggers.count == 1)
        let trigger = try #require(triggers.first)
        #expect(trigger.triggerId == "t1")
        #expect(trigger.watchPath == "/inbox")
        #expect(trigger.events == ["created", "modified"])
        #expect(trigger.filterPattern == "*.pdf")
        #expect(trigger.inputsTemplate == ["k": "v"])
        #expect(trigger.triggerCount == 7)
        #expect(trigger.debounceSeconds == 1.5)
    }

    @Test("get_trigger non-.ok surfaces as non-.ok (never a silent empty trigger)")
    func getTriggerNonOk() async throws {
        let client = makeClient { request in
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 500, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data("{\"detail\":\"boom\"}".utf8))
        }

        let response = try await client.api.getTriggerApiTriggersTriggerIdGet(
            .init(path: .init(triggerId: "t1"))
        )
        if case .ok = response {
            Issue.record("500 must not decode as .ok")
        }
    }
}
