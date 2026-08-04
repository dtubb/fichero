#if os(macOS)
@testable import Fichero
import XCTest

/// After-start attach ordering (#3773).
///
/// A library added while the sandboxed engine is already running must have its
/// security-scoped grant IN PLACE before the engine is asked to read it. Both
/// paths — folder import (ingest) and opening a `.fichero` package (load +
/// registry) — route through `FolderAccessManager.grantThenEngineWork`, which
/// must run the grant to completion FIRST. If the engine read raced ahead, the
/// library would be unreadable until the app relaunched (the exact #3773 bug).
///
/// FICHERO_APP_STORE is off in the test target, so the REAL grant is a no-op
/// here; these tests pin the ordering contract of the shared seam, which is what
/// both call paths rely on.
final class RuntimeLibraryGrantOrderingTests: XCTestCase {

    /// The grant runs, then the engine work — never the reverse.
    @MainActor
    func testGrantCompletesBeforeEngineWork() async {
        var order: [String] = []
        await FolderAccessManager.grantThenEngineWork(
            grant: { order.append("grant") },
            engineWork: { order.append("engineWork") }
        )
        XCTAssertEqual(
            order, ["grant", "engineWork"],
            "the sandbox grant must finish before the engine reads the path"
        )
    }

    /// The grant is fully AWAITED: an async grant with a real suspension point
    /// still completes before engine work begins. This is the direct regression
    /// guard against the fire-and-forget bug — a grant only kicked off (not
    /// awaited) would let engine work interleave ahead of the suspension.
    @MainActor
    func testAsyncGrantIsAwaitedNotFireAndForget() async {
        var order: [String] = []
        await FolderAccessManager.grantThenEngineWork(
            grant: {
                await Task.yield()  // force a suspension mid-grant
                order.append("grant")
            },
            engineWork: { order.append("engineWork") }
        )
        XCTAssertEqual(order, ["grant", "engineWork"])
    }

    /// The engine-work result is propagated back to the caller — the ingest
    /// response / document ids both paths consume.
    @MainActor
    func testEngineWorkResultIsReturned() async {
        let result = await FolderAccessManager.grantThenEngineWork(
            grant: {},
            engineWork: { "ingested" }
        )
        XCTAssertEqual(result, "ingested")
    }

    /// A DENIED grant stops the engine work entirely and propagates the error —
    /// the engine is never asked to read a path it can't open (the core #3773
    /// invariant: no silent proceed after a failed grant).
    @MainActor
    func testDeniedGrantPreventsEngineWork() async {
        struct GrantDenied: Error {}
        var order: [String] = []
        do {
            try await FolderAccessManager.grantThenEngineWork(
                grant: {
                    order.append("grant")
                    throw GrantDenied()
                },
                engineWork: { order.append("engineWork") }
            )
            XCTFail("expected the denied grant to propagate")
        } catch is GrantDenied {
            XCTAssertEqual(order, ["grant"], "engine work must NOT run after a denied grant")
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    /// A throwing engine-work still grants FIRST, then propagates the error —
    /// import surfaces ingest failures to the user without skipping the grant.
    @MainActor
    func testThrowingEngineWorkStillGrantsFirstThenThrows() async {
        struct IngestFailure: Error {}
        var order: [String] = []
        do {
            try await FolderAccessManager.grantThenEngineWork(
                grant: { order.append("grant") },
                engineWork: {
                    order.append("engineWork")
                    throw IngestFailure()
                }
            )
            XCTFail("expected the engine work to throw")
        } catch is IngestFailure {
            XCTAssertEqual(order, ["grant", "engineWork"])
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }
}
#endif
