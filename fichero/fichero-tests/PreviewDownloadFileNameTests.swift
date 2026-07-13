#if os(macOS)
@testable import Fichero
import XCTest

/// The Content-Disposition → cache-filename rules (#3207/#3726). These matter more
/// now that the download routes through the generated client: the header is the
/// only thing that carries the file's REAL name, and the cached file's extension
/// is what selects the QuickLook renderer. A server-supplied string is also the
/// one attacker-controllable component of the cache path, so it is sanitized.
final class PreviewDownloadFileNameTests: XCTestCase {

    private func name(_ header: String, fallback: String = "doc.pdf") -> String {
        PreviewDownloadService.preferredDownloadFileName(contentDisposition: header, fallback: fallback)
    }

    // MARK: - The header names the file

    func testPlainFilenameWins() {
        XCTAssertEqual(name("inline; filename=\"scan 12.tiff\""), "scan 12.tiff")
    }

    /// RFC 5987 `filename*` (percent-encoded UTF-8) — the engine emits this for
    /// non-ASCII names, and it takes precedence over the ASCII fallback.
    func testRFC5987FilenameIsDecodedAndPreferred() {
        let header = "inline; filename=\"diario.pdf\"; filename*=UTF-8''diario%20de%20Marshall.pdf"
        XCTAssertEqual(name(header), "diario de Marshall.pdf")
    }

    func testFallbackWhenHeaderCarriesNoFilename() {
        XCTAssertEqual(name("inline"), "doc.pdf")
    }

    // MARK: - The extension must survive (QuickLook picks the renderer from it)

    func testExtensionIsPreserved() {
        XCTAssertEqual((name("inline; filename=\"notes.md\"") as NSString).pathExtension, "md")
    }

    // MARK: - A server-supplied name can never escape the cache directory

    func testPathTraversalIsStrippedToItsLeaf() {
        XCTAssertEqual(name("inline; filename=\"../../etc/passwd\""), "passwd")
    }

    func testWindowsSeparatorsAreAlsoReducedToTheLeaf() {
        XCTAssertEqual(name("inline; filename=\"..\\\\..\\\\secret.txt\""), "secret.txt")
    }

    /// Nothing safe left in the server value → the caller's document-derived name
    /// is kept, rather than an empty or dotted path component.
    func testDotDotAloneFallsBack() {
        XCTAssertEqual(name("inline; filename=\"..\""), "doc.pdf")
    }

    func testEmptyFilenameFallsBack() {
        XCTAssertEqual(name("inline; filename=\"\""), "doc.pdf")
    }

    func testBareSlashFallsBack() {
        XCTAssertEqual(name("inline; filename=\"/\""), "doc.pdf")
    }

    func testOverlongNameIsCapped() {
        let long = String(repeating: "a", count: 500) + ".pdf"
        XCTAssertEqual(name("inline; filename=\"\(long)\"").count, 200)
    }

    func testControlCharactersAreDropped() {
        XCTAssertEqual(name("inline; filename=\"ev\u{0007}il.pdf\""), "evil.pdf")
    }

    // MARK: - sanitizedFileName directly

    func testSanitizeReturnsEmptyWhenNothingSafeRemains() {
        XCTAssertEqual(PreviewDownloadService.sanitizedFileName("/"), "")
        XCTAssertEqual(PreviewDownloadService.sanitizedFileName("."), "")
        XCTAssertEqual(PreviewDownloadService.sanitizedFileName(".."), "")
    }
}
#endif
