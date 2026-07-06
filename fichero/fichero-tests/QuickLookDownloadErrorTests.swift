#if os(macOS)
@testable import Fichero
import XCTest

/// Tests for QuickLookDownloadView.downloadErrorMessage (#3206) — the pure
/// mapping of a non-2xx source-download response to a user message. Replaces the
/// old byte-size heuristic (a legit <1000-byte .txt was misreported as an
/// error); now the engine's JSON `detail` drives the message. No live engine.
final class QuickLookDownloadErrorTests: XCTestCase {

    private func msg(_ status: Int, _ body: String?, path: String? = nil) -> String {
        QuickLookDownloadView.downloadErrorMessage(
            statusCode: status,
            body: body.map { Data($0.utf8) },
            documentPath: path
        )
    }

    func testUsesEngineJsonDetail() {
        XCTAssertEqual(msg(404, #"{"detail": "Source file not available"}"#),
                       "Source file not available")
    }

    func testFallsBackToStatusWhenNoJsonBody() {
        XCTAssertEqual(msg(500, nil), "Preview unavailable (HTTP 500)")
        XCTAssertEqual(msg(502, "not json at all"), "Preview unavailable (HTTP 502)")
    }

    /// A 422 whose `detail` is an array (FastAPI validation) isn't a plain
    /// string → fall back to the status message rather than dumping the array.
    func testNonStringDetailFallsBackToStatus() {
        XCTAssertEqual(msg(422, #"{"detail": [{"msg": "Field required"}]}"#),
                       "Preview unavailable (HTTP 422)")
    }

    /// An empty detail string is ignored (falls back), not shown blank.
    func testEmptyDetailFallsBack() {
        XCTAssertEqual(msg(404, #"{"detail": ""}"#), "Preview unavailable (HTTP 404)")
    }

    /// A linked external-drive document appends the mount hint.
    func testExternalDriveHintAppended() {
        let result = msg(404, #"{"detail": "Source file not available"}"#,
                         path: "/Volumes/Archive/scan.tif")
        XCTAssertTrue(result.hasPrefix("Source file not available"))
        XCTAssertTrue(result.contains("linked to an external drive"))
        XCTAssertTrue(result.contains("/Volumes/Archive/scan.tif"))
        XCTAssertTrue(result.contains("Mount the drive"))
    }

    func testNonExternalPathNoHint() {
        let result = msg(404, #"{"detail": "gone"}"#, path: "/library/docs/x.pdf")
        XCTAssertEqual(result, "gone")
    }
}
#endif
