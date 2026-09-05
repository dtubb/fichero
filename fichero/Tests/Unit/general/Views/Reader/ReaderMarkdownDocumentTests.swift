@testable import Fichero
import XCTest

/// A `.md` document reads as rendered Markdown in the reader (Daniel,
/// 2026-09-04). There is no `FileType.markdown` — the engine's text extractor
/// treats `.md` alongside every other text type — so the file's NAME is what
/// distinguishes it, and that rule is worth pinning.
final class ReaderMarkdownDocumentTests: XCTestCase {

    func testMarkdownExtensionsAreRecognised() {
        XCTAssertTrue(ReaderMarkdownDocument.isMarkdown(name: "NOTES.md"))
        XCTAssertTrue(ReaderMarkdownDocument.isMarkdown(name: "readme.markdown"))
        XCTAssertTrue(
            ReaderMarkdownDocument.isMarkdown(name: "Field Notes.MD"),
            "Extensions are case-insensitive; a shouted one is still Markdown."
        )
    }

    func testOtherTextFilesAreNotMarkdown() {
        XCTAssertFalse(ReaderMarkdownDocument.isMarkdown(name: "notes.txt"))
        XCTAssertFalse(ReaderMarkdownDocument.isMarkdown(name: "ledger.csv"))
        XCTAssertFalse(
            ReaderMarkdownDocument.isMarkdown(name: "story.mdx"),
            """
            MDX is a superset this renderer does not implement — claiming it \
            would render its extra syntax as literal text under a heading \
            that says Markdown.
            """
        )
    }

    func testANameWithNoExtensionIsNotMarkdown() {
        XCTAssertFalse(ReaderMarkdownDocument.isMarkdown(name: "README"))
        XCTAssertFalse(ReaderMarkdownDocument.isMarkdown(name: ""))
    }

    func testADotInTheNameIsNotAnExtension() {
        XCTAssertFalse(ReaderMarkdownDocument.isMarkdown(name: "N.C.M. Diary 1924"))
        XCTAssertTrue(
            ReaderMarkdownDocument.isMarkdown(name: "N.C.M. Diary 1924.md"),
            "Only the LAST dot names the type."
        )
    }
}
