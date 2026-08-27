@testable import Fichero
import FicheroAPIClient
import Foundation
import XCTest

/// Pins the run-trace load's cancellation policy: when a run fails and its
/// SSE stream tears the surrounding task tree down, the follow-up
/// "load run trace" request used to die with `CancellationError` and put the
/// detail pane into "Couldn't Load Run Trace" with a scary transport log.
/// `RunTraceLoadFailure.message(for:)` is the seam that decides quiet-teardown
/// vs. real failure — cancellation must map to `nil` (no error state, no
/// error-level log), everything else to user-facing text.
final class RunTraceLoadFailureTests: XCTestCase {

    private struct SampleFailure: LocalizedError {
        var errorDescription: String? { "backend exploded" }
    }

    func testPlainCancellationIsQuiet() {
        XCTAssertNil(RunTraceLoadFailure.message(for: CancellationError()))
    }

    func testURLErrorCancelledIsQuiet() {
        XCTAssertNil(RunTraceLoadFailure.message(for: URLError(.cancelled)))
    }

    func testRealFailureSurfacesLocalizedDescription() {
        XCTAssertEqual(
            RunTraceLoadFailure.message(for: SampleFailure()),
            "backend exploded"
        )
    }

    func testNonCancellationURLErrorSurfaces() {
        XCTAssertNotNil(RunTraceLoadFailure.message(for: URLError(.timedOut)))
    }
}
