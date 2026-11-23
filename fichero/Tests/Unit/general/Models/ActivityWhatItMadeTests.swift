//
//  ActivityWhatItMadeTests.swift
//  FicheroTests
//
//  `activity.window.what-it-made`: a finished workflow run's details list what it made from the run's artifacts
//  (`GET /api/artifacts/?run_id=`), then "and N more". Through the real store and generated client; only the transport
//  is stubbed. Taking a run back is not tested: it waits for `safety/run-take-back.md`.
//

@testable import Fichero
import XCTest

extension ActivityDetailsTests {
    private static func artifactsStub(count: Int, shown: Int) -> Stub {
        let items = (0..<shown).map { index in
            """
            {"id": "art-\(index)", "document_id": "doc-\(index)", "artifact_type": "transcription", "version": 1,
             "reviewed": false, "run_id": "\(runId)", "step_name": "transcribe", "created_at": "2026-10-06T12:03:00Z"}
            """
        }
        return Stub(pathSuffix: "/api/artifacts/", method: "GET", status: 200, body: Data("""
        {"items": [\(items.joined(separator: ","))], "count": \(count)}
        """.utf8))
    }

    func testWhatItMade_aFinishedWorkflowRunListsItsArtifactsThenSaysHowManyMore() async throws {
        // WHY: a finished run said nothing of what it made. One read of the run's artifacts, `run_id` and a limit, lists
        // each by name and type, opening its document, then "and N more" from the engine's count; nothing at 0.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([Self.failedStub])
        await store.loadDetails(jobId: Self.runId)
        XCTAssertNil(try details(store).made, "nothing is read yet")
        XCTAssertTrue(try details(store).madeIsRead, "a finished workflow run reads what it made")

        MockTransportURLProtocol.reset([Self.artifactsStub(count: 53, shown: 2)])
        await store.loadRunMade(threadId: Self.runId)

        let made = try XCTUnwrap(try details(store).made)
        XCTAssertEqual(made.items.map(\.documentId), ["doc-0", "doc-1"], "each opens its document")
        XCTAssertEqual(made.items.first?.name, "transcribe")
        XCTAssertEqual(made.items.first?.type, "transcription")
        XCTAssertEqual(made.more, 51, "the count less the ones listed")
        let query = try XCTUnwrap(MockTransportURLProtocol.recorded().last?.url?.query)
        XCTAssertTrue(query.contains("run_id=\(Self.runId)"), query)
        XCTAssertTrue(query.contains("limit=\(ActivityDetails.madeShown)"), query)

        MockTransportURLProtocol.reset([Self.artifactsStub(count: 0, shown: 0)])
        await store.loadRunMade(threadId: Self.runId)
        XCTAssertNil(try details(store).made, "nothing at 0")
    }

    func testWhatItMade_aRunningWorkflowRunReadsNothing() async throws {
        // WHY: only a finished run's list is read; a running one is still making them.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([Self.runningStub])
        await store.loadDetails(jobId: Self.runId)
        XCTAssertFalse(try details(store).madeIsRead)
    }
}
