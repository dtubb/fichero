@testable import Fichero
import XCTest

/// #4358 — "View Run" did nothing: the control's visibility asked whether the
/// run id was non-nil while the action ALSO required it to be non-empty, so an
/// artifact carrying an empty run id rendered an enabled control that silently
/// did nothing. One resolver answers both questions.
final class RunTraceLinkTests: XCTestCase {

    func testRealRunIdResolves() {
        XCTAssertEqual(RunTraceLink.threadId("thread-42"), "thread-42")
        XCTAssertTrue(RunTraceLink.canOpen("thread-42"))
        XCTAssertNil(
            RunTraceLink.unavailableReason("thread-42"),
            "a resolvable run needs no excuse"
        )
    }

    func testMissingRunIdCannotOpen() {
        for raw in [nil, "", "   ", "\n"] as [String?] {
            XCTAssertNil(RunTraceLink.threadId(raw))
            XCTAssertFalse(
                RunTraceLink.canOpen(raw),
                "an unrecorded run must leave the control DISABLED, never enabled-and-silent"
            )
            XCTAssertNotNil(
                RunTraceLink.unavailableReason(raw),
                "a disabled control must carry its reason for the hover"
            )
        }
    }

    func testWhitespaceIsTrimmedFromAResolvableId() {
        XCTAssertEqual(RunTraceLink.threadId("  thread-7  "), "thread-7")
    }

    /// The regression itself: enablement and action must agree for every input.
    func testEnablementAndActionNeverDisagree() {
        for raw in [nil, "", " ", "thread-1", " thread-2 "] as [String?] {
            XCTAssertEqual(
                RunTraceLink.canOpen(raw),
                RunTraceLink.threadId(raw) != nil,
                "if the control is enabled, the action must have an id to open"
            )
        }
    }
}
