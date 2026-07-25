#if os(macOS) || os(iOS)
@testable import Fichero
import XCTest

/// Tests for PreviewDownloadService.downloadErrorMessage (#3206) — the pure
/// mapping of a non-2xx source-download response to a user message. Replaces the
/// old byte-size heuristic (a legit <1000-byte .txt was misreported as an
/// error); now the engine's JSON `detail` drives the message. No live engine.
final class QuickLookDownloadErrorTests: XCTestCase {

    private func msg(_ status: Int, _ body: String?, path: String? = nil) -> String {
        PreviewDownloadService.downloadErrorMessage(
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

    // MARK: - Selection and cache lifecycle

    @MainActor
    func testRequestGateRejectsAnOldSelectionAfterReplacement() {
        let gate = PreviewDownloadService.RequestGate()
        let firstRequest = gate.begin(for: "document-a")
        let secondRequest = gate.begin(for: "document-b")

        XCTAssertFalse(gate.isCurrent(documentId: "document-a", generation: firstRequest))
        XCTAssertTrue(gate.isCurrent(documentId: "document-b", generation: secondRequest))
    }

    @MainActor
    func testRequestGateRejectsCompletionAfterDisappearance() {
        let gate = PreviewDownloadService.RequestGate()
        let request = gate.begin(for: "document-a")

        gate.invalidate()

        XCTAssertFalse(gate.isCurrent(documentId: "document-a", generation: request))
    }

    func testStalePreviewCacheFileIsRemoved() throws {
        let cacheFile = PreviewDownloadService.previewCacheDirectory
            .appendingPathComponent("stale-selection.pdf")
        try FileManager.default.createDirectory(
            at: PreviewDownloadService.previewCacheDirectory,
            withIntermediateDirectories: true
        )
        try Data("stale".utf8).write(to: cacheFile)
        defer { try? FileManager.default.removeItem(at: cacheFile) }

        PreviewDownloadService.removePreviewFile(cacheFile)

        XCTAssertFalse(FileManager.default.fileExists(atPath: cacheFile.path))
    }

    // MARK: - sanitizedFileName (#3207 path-injection guard)

    func testSanitizePassesCleanNames() {
        XCTAssertEqual(PreviewDownloadService.sanitizedFileName("report.pdf"), "report.pdf")
        XCTAssertEqual(PreviewDownloadService.sanitizedFileName("My Scan 2.tiff"), "My Scan 2.tiff")
    }

    func testSanitizeStripsPathTraversalToLeaf() {
        XCTAssertEqual(PreviewDownloadService.sanitizedFileName("../../etc/passwd"), "passwd")
        XCTAssertEqual(PreviewDownloadService.sanitizedFileName("/a/b/c.pdf"), "c.pdf")
        // Backslash (Windows) separators are stripped too.
        XCTAssertEqual(PreviewDownloadService.sanitizedFileName("..\\..\\secret.txt"), "secret.txt")
    }

    func testSanitizeRejectsEmptyAndDotOnly() {
        XCTAssertEqual(PreviewDownloadService.sanitizedFileName(""), "")
        XCTAssertEqual(PreviewDownloadService.sanitizedFileName(".."), "")
        XCTAssertEqual(PreviewDownloadService.sanitizedFileName("/"), "")
        XCTAssertEqual(PreviewDownloadService.sanitizedFileName("   "), "")
    }

    func testSanitizeStripsControlCharsAndCapsLength() {
        XCTAssertEqual(PreviewDownloadService.sanitizedFileName("a\nb\tc.pdf"), "abc.pdf")
        XCTAssertEqual(PreviewDownloadService.sanitizedFileName(String(repeating: "x", count: 500)).count, 200)
    }

    // MARK: - preferredDownloadFileName (#3202 Unicode filename handling)

    func testPreferredDownloadFileNameUsesRFC5987FilenameStar() {
        let header = "attachment; filename*=UTF-8''R%C3%A9sum%C3%A9%20Scan.pdf"
        XCTAssertEqual(
            PreviewDownloadService.preferredDownloadFileName(
                contentDisposition: header,
                fallback: "fallback.pdf"
            ),
            "Résumé Scan.pdf"
        )
    }

    func testPreferredDownloadFileNameFallsBackToQuotedFilename() {
        let header = #"attachment; filename="scan-final.pdf""#
        XCTAssertEqual(
            PreviewDownloadService.preferredDownloadFileName(
                contentDisposition: header,
                fallback: "fallback.pdf"
            ),
            "scan-final.pdf"
        )
    }

    func testPreferredDownloadFileNameKeepsFallbackWhenServerNameIsUnsafe() {
        let header = #"attachment; filename="../..""#
        XCTAssertEqual(
            PreviewDownloadService.preferredDownloadFileName(
                contentDisposition: header,
                fallback: "fallback.pdf"
            ),
            "fallback.pdf"
        )
    }
}
#endif
