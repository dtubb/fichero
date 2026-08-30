@testable import Fichero
import XCTest

/// Run comparison honesty rules (#4341, EPIC #4312).
///
/// Comparing two runs is only useful if the surface is straight about what it
/// is showing: whether the comparison could be made at all, whether the two
/// runs even read the same documents, and whether the differences listed are
/// the whole disagreement or a clipped sample.
final class RunComparisonHonestyTests: XCTestCase {

    // MARK: - Fixtures

    private func side(
        _ threadId: String,
        status: String = "completed",
        producedNothing: Int = 0,
        notRun: Int = 0
    ) -> RunComparisonSide {
        RunComparisonSide(
            threadId: threadId,
            workflowId: "wf-1",
            workflowName: "Transcribe",
            status: status,
            error: nil,
            durationMs: 1000,
            artifactCount: 2,
            stepsTotal: 4,
            stepsFailed: 0,
            stepsNotRun: notRun,
            stepsProducedNothing: producedNothing,
            resolvedDocumentCount: 3
        )
    }

    private func comparison(
        comparable: Bool = true,
        incomparableReason: String? = nil,
        identical: Bool? = false,
        sameInput: Bool? = true,
        differenceCount: Int = 1,
        costNotice: String = "Comparing means running the same input twice, so a "
            + "fresh comparison costs roughly double."
    ) -> RunComparison {
        RunComparison(
            left: side("t1"),
            right: side("t2"),
            comparable: comparable,
            incomparableReason: incomparableReason,
            sameInput: sameInput,
            inputNote: "",
            identical: identical,
            differenceCount: differenceCount,
            compared: [],
            onlyLeft: [],
            onlyRight: [],
            costNotice: costNotice
        )
    }

    // MARK: - Cost

    /// The notice must survive the trip from the wire to the model verbatim.
    /// A client that composed its own wording could drift from what the
    /// server actually charges for.
    func testCostNoticeIsCarriedThroughVerbatim() {
        let notice = comparison().costNotice
        XCTAssertTrue(notice.contains("twice"), notice)
        XCTAssertTrue(notice.lowercased().contains("double"), notice)
    }

    /// A comparison that found no differences still has to say what a fresh
    /// one would cost — that is exactly when the user considers re-running.
    func testCostNoticeIsPresentEvenWhenRunsAreIdentical() {
        let identical = comparison(identical: true, differenceCount: 0)
        XCTAssertFalse(identical.costNotice.isEmpty)
    }

    func testCostNoticeIsPresentEvenWhenRunsAreNotComparable() {
        let incomparable = comparison(
            comparable: false,
            incomparableReason: "The second run failed.",
            identical: nil
        )
        XCTAssertFalse(incomparable.costNotice.isEmpty)
    }

    // MARK: - comparable before identical

    /// `identical` is nil whenever the comparison could not be made. It must
    /// never be defaulted to false ("they differ") or true ("they agree") —
    /// two runs that both failed agree about nothing worth reporting.
    func testIncomparableRunsReportNoVerdictRatherThanAFalseOne() {
        let incomparable = comparison(
            comparable: false,
            incomparableReason: "The second run did not complete.",
            identical: nil
        )
        XCTAssertFalse(incomparable.comparable)
        XCTAssertNil(incomparable.identical)
        XCTAssertNotNil(incomparable.incomparableReason)
    }

    /// A difference count means nothing if the two runs read different
    /// documents, so that fact has to be representable.
    func testDifferentInputsAreDistinguishableFromSameInputs() {
        XCTAssertEqual(comparison(sameInput: false).sameInput, false)
        XCTAssertNil(comparison(sameInput: nil).sameInput)
    }

    // MARK: - Step counts carried from #4284

    /// A run whose steps produced nothing must not be able to present itself
    /// as a clean run in the side-by-side summary.
    func testSideCarriesProducedNothingAndNotRunCounts() {
        let empty = side("t1", producedNothing: 3, notRun: 1)
        XCTAssertEqual(empty.stepsProducedNothing, 3)
        XCTAssertEqual(empty.stepsNotRun, 1)
        XCTAssertNotEqual(empty.stepsProducedNothing, empty.stepsNotRun)
    }

    // MARK: - Clipped differences must say so

    /// Same rule as a truncated artifact preview: a partial list presented as
    /// complete is a lie about how much the two runs disagree.
    func testClippedDifferenceListsAreMarkedClipped() {
        let diff = RunTextDifference(
            kind: "changed",
            leftStartLine: 2,
            rightStartLine: 2,
            leftLines: ["firmado Ospina"],
            rightLines: ["firmado Ocampo"],
            leftLineCount: 1,
            rightLineCount: 1,
            linesTruncated: true
        )
        XCTAssertTrue(diff.linesTruncated)

        let artifact = RunArtifactComparison(
            documentId: "d1",
            documentName: "Carta",
            artifactType: "transcription",
            identical: false,
            leftProvenance: "anthropic · claude-sonnet-4-6",
            rightProvenance: "anthropic · claude-opus-4-5",
            textDifferences: [diff],
            textDifferencesTruncated: true,
            textDifferenceCount: 12,
            setDifferences: [],
            valueDifferences: []
        )
        XCTAssertTrue(artifact.textDifferencesTruncated)
        XCTAssertGreaterThan(artifact.textDifferenceCount, artifact.textDifferences.count)
    }

    /// Set differences list labels but report true counts; when the labels
    /// are a sample the counts are what the reader must trust.
    func testSetDifferenceCountsOutrankClippedLabels() {
        let set = RunSetDifference(
            fieldName: "people",
            onlyLeft: ["Ospina"],
            onlyRight: ["Ocampo"],
            sharedCount: 8,
            onlyLeftCount: 5,
            onlyRightCount: 4,
            labelsTruncated: true
        )
        XCTAssertTrue(set.labelsTruncated)
        XCTAssertGreaterThan(set.onlyLeftCount, set.onlyLeft.count)
        XCTAssertGreaterThan(set.onlyRightCount, set.onlyRight.count)
    }

    // MARK: - Provenance

    /// Two runs differing only matters once you know whether the model
    /// changed, so each side carries its own provenance.
    func testEachComparedSideCarriesItsOwnProvenance() {
        let artifact = RunArtifactComparison(
            documentId: "d1",
            documentName: nil,
            artifactType: "transcription",
            identical: false,
            leftProvenance: "anthropic · claude-sonnet-4-6",
            rightProvenance: "openai · gpt-5",
            textDifferences: [],
            textDifferencesTruncated: false,
            textDifferenceCount: 0,
            setDifferences: [],
            valueDifferences: []
        )
        XCTAssertNotEqual(artifact.leftProvenance, artifact.rightProvenance)
    }
}
