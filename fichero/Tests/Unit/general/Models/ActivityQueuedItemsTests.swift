//
//  ActivityQueuedItemsTests.swift
//  FicheroTests
//
//  `activity.window.expands-to-pages` (#5839) and `activity.log.developer-level`: a waiting kind row's pages and the
//  log's level, read through the real `ActivityStore` and generated client with only the transport stubbed. Moved out
//  of ActivityDetailsTests.swift by its length limit (#6101); the mock transport is copied, not shared, like there.
//

@testable import Fichero
import FicheroAPIClient
import XCTest

@MainActor
final class ActivityQueuedItemsTests: XCTestCase {

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

    // MARK: - activity.window.expands-to-pages

    func testQueuedKindRow_readsItsPagesThroughTheStoreInTheOrderServed() async throws {
        // WHY (#5839): a kind's row said "12 waiting" and nothing else; its details list the pages behind it, as the
        // engine serves them (the lane's order, running first), through the store and the generated client.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathSuffix: "/api/activity/jobs/kind/derivatives/items", method: "GET", status: 200, body: Data("""
            {"items": [{"id": "j1", "subject": "page-001.png", "state": "running", "reason": null},
             {"id": "j2", "subject": "page-002.png", "state": "waiting", "reason": "Waiting for a model slot"}], "count": 2}
            """.utf8))
        ])

        await store.loadQueuedItems(rowId: "waiting:derivatives")

        let items = try XCTUnwrap(store.queuedItems["derivatives"])
        XCTAssertEqual(items.map(\.subject), ["page-001.png", "page-002.png"])
        XCTAssertEqual(items.last?.reason, "Waiting for a model slot")
        XCTAssertEqual(MockTransportURLProtocol.recorded().compactMap(\.url?.path),
                       ["/api/activity/jobs/kind/derivatives/items"])
        XCTAssertTrue(MockTransportURLProtocol.recorded().first?.url?.query?.contains("limit=50") == true)
    }

    func testQueuedKindRow_aPageThatDrainedLeavesTheList() async throws {
        // WHY (## 491): the list was re-read on the details' logKey, which a kind row's has no node for, so a done page
        // stayed listed as queued. A re-read after the queue shrinks (the row's count is the key) replaces the list.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathSuffix: "/api/activity/jobs/kind/derivatives/items", method: "GET", status: 200, body: Data("""
            {"items": [{"id": "j1", "subject": "page-001.png", "state": "running", "reason": null},
             {"id": "j2", "subject": "page-002.png", "state": "waiting", "reason": null}], "count": 2}
            """.utf8))
        ])
        await store.loadQueuedItems(rowId: "waiting:derivatives")
        XCTAssertEqual(store.queuedItems["derivatives"]?.count, 2)

        MockTransportURLProtocol.reset([
            Stub(pathSuffix: "/api/activity/jobs/kind/derivatives/items", method: "GET", status: 200, body: Data("""
            {"items": [{"id": "j2", "subject": "page-002.png", "state": "running", "reason": null}], "count": 1}
            """.utf8))
        ])
        await store.loadQueuedItems(rowId: "waiting:derivatives")

        XCTAssertEqual(store.queuedItems["derivatives"]?.map(\.subject), ["page-002.png"], "page-001 is done: gone")
        XCTAssertEqual(store.queueKey(forRowId: "waiting:derivatives"), "waiting:derivatives", "no row yet: the id alone")
    }

    func testQueuedKindRow_moreCountsThePagesStillToGoNotTheDoneOnes() {
        // WHY (## 492): a kind row's total is done + queued; 12 done and 3 left, 2 listed, is 1 more, not 13.
        let store = Self.storeWithMockTransport()
        store.backgroundJobs = [ActivityJob(id: "waiting:derivatives", taskType: "derivatives", name: "Thumbnails",
                                            current: 12, total: 15, state: .waiting)]
        XCTAssertEqual(store.queuedPagesNotListed(rowId: "waiting:derivatives", listed: 2), 1)
        XCTAssertEqual(store.queuedPagesNotListed(rowId: "waiting:derivatives", listed: 3), 0)
        XCTAssertEqual(store.queuedPagesNotListed(rowId: "waiting:none", listed: 0), 0)
    }

    func testQueuedKindRow_aCountChangeChangesTheKeyThePagesAreReadOn() {
        // The list is re-read when the key changes: a page done moves the row's count, and so the key.
        let store = Self.storeWithMockTransport()
        func key(_ done: Int) -> String {
            store.backgroundJobs = [ActivityJob(id: "waiting:derivatives", taskType: "derivatives", name: "Thumbnails",
                                                current: done, total: 15, state: .waiting)]
            return store.queueKey(forRowId: "waiting:derivatives")
        }
        XCTAssertNotEqual(key(12), key(13))
        XCTAssertEqual(key(13), key(13), "unchanged row, unchanged key: no needless re-read")
    }

    func testQueuedKind_onlyAWaitingOrPausedKindRowHasPages() {
        XCTAssertEqual(ActivityStore.queuedKind(ofRowId: "waiting:ask-a-model"), "ask-a-model")
        XCTAssertEqual(ActivityStore.queuedKind(ofRowId: "paused:derivatives"), "derivatives")
        XCTAssertNil(ActivityStore.queuedKind(ofRowId: "waiting:"))
        XCTAssertNil(ActivityStore.queuedKind(ofRowId: "page-1"))
    }

    func testActivityDetailsLog_theDeveloperLevelAsksForTheDebugLinesAndTheDefaultDoesNot() async throws {
        // WHY (`activity.log.developer-level`): the person's log is the default; Developer adds `?detail=developer`.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathSuffix: "/api/activity/jobs/page-1/log", method: "GET", status: 200, body: Data("""
            {"job_id": "page-1", "lines": [
              {"timestamp": "2026-10-06T12:00:30+00:00", "level": "info", "message": "Node 'read' started",
               "job_id": "page-1", "detail": "developer"}
            ]}
            """.utf8))
        ])

        await store.loadJobLog(jobId: "page-1")
        await store.loadJobLog(jobId: "page-1", developer: true)

        let queries = MockTransportURLProtocol.recorded().map { $0.url?.query ?? "" }
        XCTAssertEqual(queries.count, 2)
        XCTAssertFalse(queries[0].contains("developer"), "the person's log is the default")
        XCTAssertTrue(queries[1].contains("detail=developer"))
        XCTAssertEqual(store.jobLogs["page-1"]?.first?.message, "Node 'read' started")
    }
}
