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
        let schedules = try okResponse.body.json.items.map { ScheduleInfo(response: $0) }
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

    @Test("automation date round-trips: parseEngineDate ↔ ISO8601FormatStyle re-encode identically")
    func automationDateRoundTrips() throws {
        // The mapper formats Date→String with this exact style; parseEngineDate reads
        // String→Date on the way back in. They're two different parsers, so lock that
        // a canonical wire string decodes to the right Date and re-encodes identically.
        let format = Date.ISO8601FormatStyle(includingFractionalSeconds: true)
        let wire = "2026-07-04T12:34:56.789Z"
        let date = try #require(parseEngineDate(wire))
        #expect(date.formatted(format) == wire)
    }

    @Test("createSchedule raises on a malformed run_at instead of silently dropping it")
    func createScheduleRaisesOnMalformedDate() async throws {
        // The bad date is rejected while building the request body, before any network
        // call — so the default APIClient session never fires. Guards the fix that
        // replaced `.flatMap(parseEngineDate)` (silent nil) with a raising parse.
        let service = AutomationService(
            apiClient: APIClient(baseURL: URL(string: "https://test.fichero")!)
        )
        let config = ScheduleConfigRequest(
            scheduleType: "once", cronExpression: nil, intervalSeconds: nil,
            runAt: "not-a-date", timezone: "UTC",
            startDate: nil, endDate: nil, maxRuns: nil
        )
        let request = CreateScheduleRequest(
            name: "x", workflowId: "wf", config: config,
            inputs: [:], useBatch: false, batchItems: [], maxConcurrent: 1
        )
        await #expect(throws: AutomationServiceError.self) {
            _ = try await service.createSchedule(request: request)
        }
    }

    @Test("AutomationService surfaces a 422's detail as validationError")
    func getScheduleValidationErrorPreservesDetail() async throws {
        let service = AutomationService(apiClient: APIClient(client: makeClient { request in
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 422, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            let body = #"{"detail":[{"loc":["body","name"],"msg":"field required","type":"missing"}]}"#
            return (response, Data(body.utf8))
        }))
        do {
            _ = try await service.getSchedule(scheduleId: "s1")
            Issue.record("expected a throw on 422")
        } catch let AutomationServiceError.validationError(message) {
            #expect(message.contains("field required"))
        } catch {
            Issue.record("expected .validationError, got \(error)")
        }
    }

    @Test("AutomationService.listSchedules throws on a 500 (never a silently empty list)")
    func listSchedulesThrowsOn500() async throws {
        let service = AutomationService(apiClient: APIClient(client: makeClient { request in
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 500, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data(#"{"detail":"boom"}"#.utf8))
        }))
        await #expect(throws: AutomationServiceError.self) {
            _ = try await service.listSchedules()
        }
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
