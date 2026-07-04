//
//  SchedulesMigrationTests.swift
//  FicheroTests
//
//  #3030 (post-#3131 typed ops) — AutomationService schedule ops migrated off
//  the hand-rolled APIClient onto the generated typed operations. These decode a
//  real ScheduleResponse envelope through the generated client and run it through
//  the ScheduleInfo mapper, locking the tricky bits: the typed `inputs` /
//  `batch_items` payloads map to [String:String] / [[String:String]], and the
//  list endpoint's items decode. Reuses MockURLProtocol (same test target).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
struct SchedulesMigrationTests {

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

    private static let scheduleJSON = """
    {"schedule_id":"s1","name":"Nightly","workflow_id":"wf1","schedule_type":"interval",
     "cron_expression":null,"interval_seconds":3600,"run_at":null,"timezone":"UTC",
     "status":"active","inputs":{"k":"v"},"use_batch":true,
     "batch_items":[{"a":"b"},{"c":"d"}],"max_concurrent":2,
     "created_at":"2026-07-04T00:00:00Z","updated_at":"2026-07-04T00:00:00Z",
     "last_run_at":null,"next_run_at":null,"run_count":5,"error_message":null}
    """

    @Test("list_schedules decodes + maps items into ScheduleInfo (inputs/batch_items typed)")
    func listSchedulesMaps() async throws {
        let client = makeClient { request in
            #expect(request.url?.path == "/api/schedules")
            #expect((request.url?.query ?? "").contains("limit=100"))
            let json = "{\"count\":1,\"items\":[\(Self.scheduleJSON)]}"
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data(json.utf8))
        }

        let response = try await client.api.listSchedulesApiSchedulesGet(
            .init(query: .init(limit: 100))
        )
        guard case .ok(let okResponse) = response else {
            Issue.record("expected .ok")
            return
        }
        let schedules = try okResponse.body.json.items.map(ScheduleInfo.init)
        #expect(schedules.count == 1)
        let schedule = try #require(schedules.first)
        #expect(schedule.scheduleId == "s1")
        #expect(schedule.intervalSeconds == 3600)
        #expect(schedule.cronExpression == nil)
        #expect(schedule.inputs == ["k": "v"])
        #expect(schedule.batchItems?.count == 2)
        #expect(schedule.batchItems?.first == ["a": "b"])
        #expect(schedule.runCount == 5)
    }

    @Test("get_schedule non-.ok surfaces as non-.ok (never a silent empty schedule)")
    func getScheduleNonOk() async throws {
        let client = makeClient { request in
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 500, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data("{\"detail\":\"boom\"}".utf8))
        }

        let response = try await client.api.getScheduleApiSchedulesScheduleIdGet(
            .init(path: .init(scheduleId: "s1"))
        )
        if case .ok = response {
            Issue.record("500 must not decode as .ok")
        }
    }
}
