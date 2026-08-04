@testable import Fichero
import XCTest

/// A dropped URL must be recognised for what it is before anything imports it
/// (#2386).
///
/// ## What was wrong
///
/// `classifyDroppedURLs` had two buckets — Fichero library packages, and
/// "everything else, import it". There was **no scheme check anywhere in the
/// import path**, so a link dragged from a browser handed
/// `https://example.org/paper.pdf` to the importer as a file path. The
/// importer then failed on a path that does not exist, and the user saw a drop
/// that did nothing at all.
///
/// That is half of "PDF import must work from link and drag/drop": not a bug
/// in the download, but the absence of any notion that a remote URL is
/// different from a file.
///
/// ## What these tests do and do not prove
///
/// They prove CLASSIFICATION: which bucket each URL shape lands in. They do
/// **not** prove DELIVERY — that a document exists afterwards with content in
/// the right parent — because that needs a running app, a drag session and a
/// live engine. #3390, #702 and #570 were all closed on classification and
/// Daniel still reports drops failing, so classification alone is explicitly
/// not the standard (#4473). The untested shapes are named in the commit.
final class DroppedURLClassificationTests: XCTestCase {

    /// Returns the named type rather than the tuple it replaced: the members
    /// are spelled the same, so every assertion below reads unchanged, and a
    /// third bucket added later cannot be silently dropped by a tuple that
    /// still lists two.
    private func classify(_ urls: [URL]) -> DroppedURLs {
        DroppedURLs.classify(urls)
    }

    // MARK: - The bug: a web link is not a file

    func testAnHTTPSLinkIsRemoteNotSomethingToImport() {
        let result = classify([URL(string: "https://example.org/paper.pdf")!])

        XCTAssertEqual(result.remoteURLs.map(\.absoluteString),
                       ["https://example.org/paper.pdf"])
        XCTAssertTrue(
            result.importURLs.isEmpty,
            "a URL with no file on disk must never reach the importer as a path"
        )
    }

    func testPlainHTTPIsAlsoRemote() {
        XCTAssertEqual(classify([URL(string: "http://example.org/a.pdf")!]).remoteURLs.count, 1)
    }

    /// Bucketed by what the URL IS, not by a scheme allowlist — so a scheme
    /// nobody thought about cannot fall through to the importer.
    func testAnUnexpectedSchemeIsRemoteRatherThanImported() {
        for raw in ["mailto:someone@example.org", "ftp://example.org/a.pdf", "about:blank"] {
            let result = classify([URL(string: raw)!])
            XCTAssertTrue(result.importURLs.isEmpty, "\(raw) must not be imported as a file")
            XCTAssertEqual(result.remoteURLs.count, 1, "\(raw) should be recognised as remote")
        }
    }

    // MARK: - ...and the local path still works

    /// The control. If everything were bucketed as remote, every test above
    /// would pass and drag-and-drop would be completely broken — which is a
    /// worse bug than the one being fixed.
    func testALocalFileURLIsStillImported() {
        let file = URL(fileURLWithPath: "/tmp/paper.pdf")
        let result = classify([file])

        XCTAssertEqual(result.importURLs, [file])
        XCTAssertTrue(result.remoteURLs.isEmpty)
    }

    func testAMixedDropSplitsRatherThanFailingWholesale() {
        let file = URL(fileURLWithPath: "/tmp/local.pdf")
        let link = URL(string: "https://example.org/remote.pdf")!

        let result = classify([file, link])

        XCTAssertEqual(result.importURLs, [file], "the local file still imports")
        XCTAssertEqual(result.remoteURLs, [link], "and the link is reported, not silently dropped")
    }

    // MARK: - Library packages keep their own bucket

    func testAFicheroPackageIsNotAnImport() {
        let library = URL(fileURLWithPath: "/tmp/Archive.fichero")
        let result = classify([library])

        // The package check reads filesystem attributes, so a non-existent path
        // may fall through to `importURLs` — what must NOT happen is that it is
        // treated as remote, which would break opening a library by drop.
        XCTAssertTrue(result.remoteURLs.isEmpty)
    }

    func testAnEmptyDropClassifiesToNothing() {
        let result = classify([])

        XCTAssertTrue(result.libraryURLs.isEmpty)
        XCTAssertTrue(result.importURLs.isEmpty)
        XCTAssertTrue(result.remoteURLs.isEmpty)
    }

    // MARK: - The surfaces agree on one extraction

    /// Every external drop target must reach `ExternalFileDropLoader`. The
    /// window-level target used to declare `.dropDestination(for: URL.self)`,
    /// which is only ever OFFERED droppables that can vend a URL — so a
    /// promised file or `public.pdf` data with no URL was never seen by it,
    /// while the detail column's provider-based target would have accepted it.
    ///
    /// Since the window-level target sits ABOVE the others, that made
    /// acceptance depend on which surface caught the drop, which is exactly
    /// "works from some locations".
    func testNoDropSurfaceStillUsesTheURLTypedDestination() throws {
        let source = try AppSource.text("Views/Shell/ContentView/ContentViewModifiers.swift")

        // Assert about CODE, not commentary: the file's doc comment narrates
        // the deleted modifier's history and rightly names it verbatim, so a
        // raw contains() would fail on the explanation of the fix itself.
        let code = source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
        XCTAssertFalse(
            code.contains("dropDestination(for: URL.self)"),
            "the window-level drop must take providers, so it can be offered the "
                + "same droppables every other surface accepts (#2386 / #4458)"
        )
        XCTAssertFalse(
            code.contains(".onDrop("),
            "no drop target of ANY type may be re-mounted window-wide (#4458/#4520)"
        )
        // …and the provider path it was replaced by is NOT here either. #2386
        // put it on the WHOLE `NavigationSplitView`, which is the scope #4458
        // exists to undo; the provider handler lives on `detailColumn`, where
        // `ContentPaneDropTargetTests` pins it. Asserting the handler's
        // presence in this file is what let the wrong scope read as fixed.
        let layout = try AppSource.text(
            "Views/Shell/ContentView/Layout/ContentView+RootLayout.swift"
        )
        XCTAssertTrue(
            layout.contains("handleContentPaneExternalDrop(providers)"),
            "the provider path must still be reached — from the detail column"
        )
    }
}
