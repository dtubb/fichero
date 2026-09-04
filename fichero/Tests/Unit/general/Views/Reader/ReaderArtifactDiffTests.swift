@testable import Fichero
import XCTest

/// The reader's artifact comparison (Daniel, 2026-09-04: "a 2–5-way diff of
/// artifact results — three transcription reviews side by side with the
/// differences highlighted"). The diff is pure so it can be tested here rather
/// than eyeballed through a WKWebView: "the highlighting is subtly wrong" is
/// not something a manuscript reader can be expected to notice.
final class ReaderArtifactDiffTests: XCTestCase {

    // MARK: - Word-level diff

    func testIdenticalTextsProduceNoChanges() {
        let comparison = ReaderArtifactDiff.compare(
            baseline: "otorgamos que damos", variant: "otorgamos que damos"
        )
        XCTAssertTrue(comparison.isIdentical)
        XCTAssertEqual(comparison.segments, [.same("otorgamos que damos")])
        XCTAssertEqual(comparison.granularity, .word)
    }

    func testAReplacedWordReadsAsARemovalThenAnInsertion() {
        let comparison = ReaderArtifactDiff.compare(
            baseline: "tomar la confesion", variant: "tomar la confession"
        )
        XCTAssertEqual(
            comparison.segments,
            [.same("tomar la"), .removed("confesion"), .inserted("confession")],
            "A replacement must read 'was X, now Y' — deletion first, in place."
        )
        XCTAssertEqual(comparison.changeCount, 2)
    }

    func testAnInsertionIsMarkedWithoutDisturbingTheSurroundingText() {
        let comparison = ReaderArtifactDiff.compare(
            baseline: "del mal tratado", variant: "del muy mal tratado"
        )
        XCTAssertEqual(
            comparison.segments,
            [.same("del"), .inserted("muy"), .same("mal tratado")]
        )
    }

    func testAdjacentChangesCollapseIntoOneRun() {
        let comparison = ReaderArtifactDiff.compare(
            baseline: "uno dos tres", variant: "uno cuatro cinco"
        )
        XCTAssertEqual(
            comparison.segments,
            [.same("uno"), .removed("dos tres"), .inserted("cuatro cinco")],
            "A changed phrase is marked once, not once per word."
        )
    }

    func testAnEmptyVariantIsAllRemoval() {
        let comparison = ReaderArtifactDiff.compare(baseline: "algo aqui", variant: "")
        XCTAssertEqual(comparison.segments, [.removed("algo aqui")])
    }

    func testAnEmptyBaselineIsAllInsertion() {
        let comparison = ReaderArtifactDiff.compare(baseline: "", variant: "algo aqui")
        XCTAssertEqual(comparison.segments, [.inserted("algo aqui")])
    }

    func testPunctuationStaysAttachedToItsWord() {
        let comparison = ReaderArtifactDiff.compare(baseline: "quales", variant: "quales,")
        XCTAssertEqual(
            comparison.changeCount, 2,
            "One edited word is one word removed and one added, not two separate edits plus a comma."
        )
    }

    // MARK: - Granularity

    func testLongTextsFallBackToLineLevelAndSaySo() {
        let long = (0..<(ReaderArtifactDiff.wordDiffTokenLimit + 10))
            .map { "palabra\($0)" }
            .joined(separator: " ")
        let comparison = ReaderArtifactDiff.compare(baseline: long, variant: long)
        XCTAssertEqual(
            comparison.granularity, .line,
            "Past the cap the word-level table costs more than it is worth — so it drops to lines."
        )
        XCTAssertTrue(
            comparison.isIdentical,
            "A coarser comparison of two identical texts still reports no differences."
        )
        XCTAssertEqual(comparison.granularity.caption, "line-level")
    }

    // MARK: - HTML

    func testFewerThanTwoColumnsSaysSoRatherThanRenderingNothing() {
        let html = ReaderArtifactDiff.html(columns: [.init(title: "One", text: "a")])
        XCTAssertTrue(html.contains("Pick two or more artifacts to compare."))
    }

    func testTheFirstColumnIsNamedAsTheBaseline() {
        let html = ReaderArtifactDiff.html(columns: [
            .init(title: "Review 1", text: "uno dos"),
            .init(title: "Review 2", text: "uno tres")
        ])
        XCTAssertTrue(html.contains("Compared against <strong>Review 1</strong>"))
        XCTAssertTrue(html.contains("<del>dos</del>"))
        XCTAssertTrue(html.contains("<ins>tres</ins>"))
    }

    func testEveryVariantIsComparedAgainstTheSameBaseline() {
        let html = ReaderArtifactDiff.html(columns: [
            .init(title: "Base", text: "uno dos"),
            .init(title: "Review A", text: "uno dos"),
            .init(title: "Review B", text: "uno tres")
        ])
        XCTAssertTrue(html.contains("Review A"))
        XCTAssertTrue(html.contains("Review B"))
        XCTAssertTrue(
            html.contains("identical"),
            "A variant that matches the baseline says so — that is the answer to 'which one is the outlier'."
        )
    }

    func testTheChangeCountIsPrintedInTheHeader() {
        let html = ReaderArtifactDiff.html(columns: [
            .init(title: "Base", text: "uno dos"),
            .init(title: "Other", text: "uno tres")
        ])
        XCTAssertTrue(html.contains("2 words differ"))
    }

    func testMarkupInTheTranscriptionIsEscapedRatherThanExecuted() {
        let html = ReaderArtifactDiff.html(columns: [
            .init(title: "Base", text: "plain"),
            .init(title: "<script>alert(1)</script>", text: "a & b <em>x</em>")
        ])
        XCTAssertFalse(html.contains("<script>"), "A title is text, never markup.")
        XCTAssertTrue(html.contains("&lt;em&gt;"))
        XCTAssertTrue(html.contains("&amp;"))
    }

    func testTheRenderedPageDeclaresBothAppearances() {
        let html = ReaderArtifactDiff.html(columns: [
            .init(title: "A", text: "x"), .init(title: "B", text: "y")
        ])
        XCTAssertTrue(
            html.contains("color-scheme: light dark"),
            "The comparison is a reader surface, not a web page that ignores the system appearance."
        )
        XCTAssertTrue(html.contains("-apple-system-body"), "Semantic system fonts only.")
    }
}
