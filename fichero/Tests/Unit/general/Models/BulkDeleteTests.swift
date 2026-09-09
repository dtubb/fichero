@testable import Fichero
import XCTest

/// spec: kg-tables — `kg.scale.bulk-correctness`. A bulk delete prunes exactly the rows
/// that SUCCEEDED (a partial failure never leaves an already-deleted row visible), with
/// bounded concurrency. The pure `chunked` window and the success-collection are pinned
/// here without a live service.
@MainActor
final class BulkDeleteTests: XCTestCase {

    func testChunkedSplitsIntoWaves() {
        XCTAssertEqual([1, 2, 3, 4, 5].chunked(into: 2), [[1, 2], [3, 4], [5]])
        XCTAssertEqual([1, 2, 3].chunked(into: 3), [[1, 2, 3]])
        XCTAssertEqual([Int]().chunked(into: 4), [])
    }

    func testChunkedNonPositiveSizeIsOneChunk() {
        XCTAssertEqual([1, 2, 3].chunked(into: 0), [[1, 2, 3]])
        XCTAssertEqual([Int]().chunked(into: 0), [])
    }

    func testSucceedingReturnsOnlyIdsThatSucceeded() async {
        let ids = (1...20).map { "id-\($0)" }
        let doomed: Set<String> = ["id-5", "id-13"]  // these "fail" to delete
        let succeeded = await BulkDelete.succeeding(ids: ids, maxConcurrent: 4) { id in
            !doomed.contains(id)  // false => delete failed
        }
        XCTAssertEqual(Set(succeeded), Set(ids).subtracting(doomed))
        XCTAssertFalse(succeeded.contains("id-5"))
        XCTAssertFalse(succeeded.contains("id-13"))
    }

    func testSucceedingAttemptsEveryId() async {
        let ids = (1...10).map { "id-\($0)" }
        let attempted = Attempted()
        _ = await BulkDelete.succeeding(ids: ids, maxConcurrent: 3) { id in
            await attempted.add(id)
            return true
        }
        let seen = await attempted.snapshot()
        XCTAssertEqual(seen, Set(ids))
    }

    func testEmptyIsNoOp() async {
        let succeeded = await BulkDelete.succeeding(ids: []) { _ in true }
        XCTAssertTrue(succeeded.isEmpty)
    }

    /// Thread-safe recorder: the delete op is @Sendable and its waves run concurrently.
    private actor Attempted {
        private var ids: Set<String> = []
        func add(_ id: String) { ids.insert(id) }
        func snapshot() -> Set<String> { ids }
    }
}
