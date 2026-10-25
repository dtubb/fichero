//
//  ActivityLogAndGridStoreTests.swift
//  FicheroTests
//
//  `activity.log.problems-first` and `activity.window.page-grid` (ported from m-bugs-window-c16): the store's reads of a row's
//  log by level and of a run's page dots by stage, through the real store with only the transport stubbed.
//

@testable import Fichero
import FicheroAPIClient
import XCTest

@MainActor
final class ActivityLogAndGridStoreTests: XCTestCase {

    private typealias Stub = ActivityStubbedResponse
    private typealias MockTransportURLProtocol = ActivityMockTransport

    override func setUp() {
        super.setUp()
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
        MockTransportURLProtocol.reset([])
    }

    private static func storeWithMockTransport() -> ActivityStore {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockTransportURLProtocol.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/ActivityQueuedItemsTests.fichero",
            session: URLSession(configuration: configuration)
        )
        return ActivityStore(service: ActivityService(ficheroClient: client))
    }

    func testPageGrid_aStageAsksForThatStageAndIsKeptApart() async throws {
        // WHY (`activity.window.page-grid`): the dots for one stage are not the worst-across-stages dots.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathSuffix: "/api/activity/jobs/run/pages", method: "GET", status: 200, body: Data("""
            {"job_id": "run", "total": 1, "items": [{"document_id": "p1", "name": "p1", "state": "failed"}]}
            """.utf8))
        ])
        await store.loadPageGrid(jobId: "run")
        await store.loadPageGrid(jobId: "run", stage: "read")

        let queries = MockTransportURLProtocol.recorded().map { $0.url?.query ?? "" }
        XCTAssertFalse(queries[0].contains("stage="))
        XCTAssertTrue(queries[1].contains("stage=read"))
        XCTAssertNotNil(store.pageGrids["run"])
        XCTAssertNotNil(store.pageGrids[ActivityStore.pageGridKey(jobId: "run", stage: "read")])
        XCTAssertEqual(ActivityStore.pageGridKey(jobId: "run", stage: "read"), "run|read")
    }

    func testActivityDetailsLog_theStoreKnowsWhetherARowsLogHasAProblem() async throws {
        // WHY (`activity.log.problems-first`): the filter row defaults to Problems while the log has a warning or an error;
        // a read of all the lines says so, and a Problems read (all problems) keeps it.
        let store = Self.storeWithMockTransport()
        func stub(_ level: String) -> Stub {
            Stub(pathSuffix: "/api/activity/jobs/page-1/log", method: "GET", status: 200, body: Data("""
            {"job_id": "page-1", "lines": [{"level": "\(level)", "message": "m", "job_id": "page-1"}]}
            """.utf8))
        }
        MockTransportURLProtocol.reset([stub("info")])
        await store.loadJobLog(jobId: "page-1")
        XCTAssertEqual(store.jobLogHasProblems["page-1"], false)

        MockTransportURLProtocol.reset([stub("warning")])
        await store.loadJobLog(jobId: "page-1")
        XCTAssertEqual(store.jobLogHasProblems["page-1"], true)

        MockTransportURLProtocol.reset([stub("warning")])
        await store.loadJobLog(jobId: "page-1", problemsOnly: true)
        XCTAssertEqual(store.jobLogHasProblems["page-1"], true, "a Problems read that returns lines")
        XCTAssertTrue(MockTransportURLProtocol.recorded().first?.url?.query?.contains("level=problems") == true)
    }
}
