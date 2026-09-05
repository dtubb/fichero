@testable import Fichero
import XCTest

/// `OCRGeometryBox.confidence` was decoded since #4309 and read by nothing:
/// in Daniel's live library, 7,595 boxes at 0.50 and 6,225 at 0.30 drawn
/// exactly as authoritatively as the 1,557 at 1.0. The boxes exist to make a
/// transcription checkable rather than trusted, and a uniform stroke over a
/// 0.30 box quietly undoes that.
final class OCRBoxConfidenceTests: XCTestCase {

    private func box(_ confidence: Double?, text: String = "word") -> OCRGeometryBox {
        OCRGeometryBox(text: text, bbox: [0, 0, 0.1, 0.1], level: "word", confidence: confidence)
    }

    // MARK: - The threshold

    func testTheObservedClustersFallEitherSideOfTheThreshold() {
        XCTAssertFalse(OCRBoxConfidence.isUncertain(1.0))
        XCTAssertTrue(OCRBoxConfidence.isUncertain(0.5))
        XCTAssertTrue(OCRBoxConfidence.isUncertain(0.3))
    }

    func testExactlyAtTheThresholdIsCertain() {
        XCTAssertFalse(
            OCRBoxConfidence.isUncertain(OCRBoxConfidence.certainAtOrAbove),
            "The boundary is inclusive — 'at or above' is what the name says."
        )
        XCTAssertTrue(
            OCRBoxConfidence.isUncertain(OCRBoxConfidence.certainAtOrAbove - 0.0001)
        )
    }

    /// The rule that keeps the two axes apart. A missing confidence means the
    /// producer does not report one — the alignment pass writes none — and
    /// dimming every box from a silent engine would state a doubt the data
    /// never expressed. What is true of those boxes is PROVENANCE, which owns
    /// its own visual channel.
    func testAnUnreportedConfidenceIsNotDoubt() {
        XCTAssertFalse(OCRBoxConfidence.isUncertain(nil))
        XCTAssertFalse(OCRBoxConfidence.isUncertain(box(nil)))
    }

    // MARK: - What the rendering asks it

    func testAnUncertainBoxIsRecessiveButStillDrawn() {
        let dim = OCRBoxConfidence.strokeOpacity(0.3)
        let firm = OCRBoxConfidence.strokeOpacity(1.0)
        XCTAssertLessThan(dim, firm)
        XCTAssertGreaterThan(dim, 0, "Recessive, not invisible — it must stay findable.")
    }

    /// Inline text is the strongest claim the overlay makes: it prints what
    /// the machine believes the word says, in place of the word. Over a box
    /// the machine is 30% sure of, that asserts twice.
    func testALowConfidenceBoxNeverPrintsItsWordOverTheScan() {
        XCTAssertFalse(OCRBoxConfidence.drawsInlineText(0.3))
        XCTAssertTrue(OCRBoxConfidence.drawsInlineText(1.0))
        XCTAssertTrue(
            OCRBoxConfidence.drawsInlineText(nil),
            "An engine that reports no confidence has not said the word is wrong."
        )
    }

    // MARK: - The countable half

    func testTheCountAndSummaryNameHowMuchOfHowMany() {
        let boxes = [box(1.0), box(0.5), box(0.3), box(nil)]
        XCTAssertEqual(OCRBoxConfidence.uncertainCount(in: boxes), 2)
        XCTAssertEqual(
            OCRBoxConfidence.summary(for: boxes),
            "2 of 4 below 80% confidence",
            "\"12 uncertain\" reads very differently over 15 boxes than over 1,500."
        )
    }

    func testAConfidentPageWarnsAboutNothing() {
        XCTAssertNil(OCRBoxConfidence.summary(for: [box(1.0), box(0.9), box(nil)]))
        XCTAssertNil(OCRBoxConfidence.summary(for: []))
    }

    func testTheOverlaySummarySpeaksTheDoubtToo() {
        let uncertain = OCRGeometryOverlay.accessibilitySummary(for: [box(1.0), box(0.3)])
        XCTAssertTrue(uncertain.contains("1 of 2 below 80% confidence"))
        let confident = OCRGeometryOverlay.accessibilitySummary(for: [box(1.0)])
        XCTAssertFalse(
            confident.contains("below"),
            "A page with nothing to warn about says nothing — the label is not a lecture."
        )
    }
}
