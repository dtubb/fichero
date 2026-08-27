@testable import Fichero
import XCTest

/// Pure grouping/ordering rules for the provenance-first artifact browser
/// (#4319): group by run newest-first, pipeline `sequence` order within a
/// run, ungrouped legacy artifacts collapse into a trailing "Earlier"
/// section — never hidden.
final class ArtifactRunGroupingTests: XCTestCase {

    private func artifact(
        id: String,
        runId: String? = nil,
        workflowId: String? = nil,
        sequence: Int? = nil,
        type: String = "transcription",
        createdAt: Date
    ) -> Artifact {
        Artifact(
            id: id,
            documentId: "doc-1",
            artifactType: type,
            runId: runId,
            workflowId: workflowId,
            sequence: sequence,
            createdAt: createdAt
        )
    }

    private let base = Date(timeIntervalSince1970: 1_750_000_000)

    // MARK: - Grouping

    func testGroupsByRunNewestRunFirstWithEarlierLast() {
        let items = [
            artifact(id: "old-run-a", runId: "run-old", sequence: 1, createdAt: base),
            artifact(id: "legacy", createdAt: base.addingTimeInterval(500)),
            artifact(id: "new-run-a", runId: "run-new", sequence: 1, createdAt: base.addingTimeInterval(1000))
        ]

        let groups = ArtifactRunGrouping.groups(from: items)

        XCTAssertEqual(groups.map(\.id), ["run-new", "run-old", "earlier"])
        XCTAssertTrue(groups.last!.isEarlier)
        // Nothing hidden: every artifact lands in exactly one group.
        XCTAssertEqual(groups.flatMap(\.artifacts).count, items.count)
    }

    func testEnsemblePassesReadInPipelineOrderWithinOneGroup() {
        // Three transcribe passes of one ensemble run, saved out of order.
        let items = [
            artifact(id: "pass-3", runId: "run-1", sequence: 3, createdAt: base.addingTimeInterval(30)),
            artifact(id: "pass-1", runId: "run-1", sequence: 1, createdAt: base.addingTimeInterval(10)),
            artifact(id: "pass-2", runId: "run-1", sequence: 2, createdAt: base.addingTimeInterval(20))
        ]

        let groups = ArtifactRunGrouping.groups(from: items)

        XCTAssertEqual(groups.count, 1)
        XCTAssertEqual(groups[0].artifacts.map(\.id), ["pass-1", "pass-2", "pass-3"])
    }

    func testLegacyRowsWithoutSequenceSortAfterSequencedOnesByCreation() {
        let items = [
            artifact(id: "no-seq-late", runId: "run-1", createdAt: base.addingTimeInterval(99)),
            artifact(id: "no-seq-early", runId: "run-1", createdAt: base.addingTimeInterval(1)),
            artifact(id: "seq-2", runId: "run-1", sequence: 2, createdAt: base.addingTimeInterval(50))
        ]

        let groups = ArtifactRunGrouping.groups(from: items)

        XCTAssertEqual(
            groups[0].artifacts.map(\.id),
            ["seq-2", "no-seq-early", "no-seq-late"]
        )
    }

    func testEmptyOrWhitespaceRunIdCountsAsEarlier() {
        let items = [
            artifact(id: "blank", runId: "  ", createdAt: base),
            artifact(id: "empty", runId: "", createdAt: base)
        ]

        let groups = ArtifactRunGrouping.groups(from: items)

        XCTAssertEqual(groups.count, 1)
        XCTAssertTrue(groups[0].isEarlier)
        XCTAssertEqual(Set(groups[0].artifacts.map(\.id)), ["blank", "empty"])
    }

    func testGroupCarriesWorkflowIdAndLatestTimestamp() {
        let items = [
            artifact(id: "a", runId: "run-1", workflowId: "wf-9", sequence: 1, createdAt: base),
            artifact(id: "b", runId: "run-1", sequence: 2, createdAt: base.addingTimeInterval(60))
        ]

        let groups = ArtifactRunGrouping.groups(from: items)

        XCTAssertEqual(groups[0].workflowId, "wf-9")
        XCTAssertEqual(groups[0].latestCreatedAt, base.addingTimeInterval(60))
    }

    func testNoItemsYieldsNoGroups() {
        XCTAssertEqual(ArtifactRunGrouping.groups(from: []), [])
    }

    // MARK: - Earlier section keeps the old type-grouped order

    func testEarlierSectionKeepsCleanPairGrouping() {
        let items = [
            artifact(id: "people-raw", type: "people", createdAt: base.addingTimeInterval(10)),
            artifact(id: "people-clean", type: "people_clean", createdAt: base),
            artifact(id: "dates", type: "dates", createdAt: base)
        ]

        let groups = ArtifactRunGrouping.groups(from: items)

        XCTAssertEqual(groups.count, 1)
        // dates < people; within "people", the cleaned canonical entry first.
        XCTAssertEqual(
            groups[0].artifacts.map(\.id),
            ["dates", "people-clean", "people-raw"]
        )
    }
}

// MARK: - Totality: an artifact cannot vanish into the grouping (#4348)

extension ArtifactRunGroupingTests {

    /// Every artifact reaches exactly one section, for EVERY shape the field
    /// can take — not just the one arrangement the fixture above happens to use.
    ///
    /// #4348 reports an artifact appearing and then vanishing. The issue's own
    /// prime suspect is this grouping: an artifact whose `runId`/`sequence`
    /// arrives in a SECOND update could be regrouped into a section that is
    /// collapsed or off-screen — present in the store, absent from the eye.
    ///
    /// Reading the code says that cannot happen: `groups(from:)` partitions on
    /// `normalized(runId)`, so every artifact lands in a run group or in
    /// `earlier`, and both are returned. This asserts the property rather than
    /// the reading, across the shapes that regrouping actually produces —
    /// including the mid-flight one where `runId` is present but `sequence` is
    /// not yet.
    func testEveryArtifactShapeReachesExactlyOneSection() {
        let items: [Artifact] = [
            artifact(id: "a", runId: "run-1", sequence: 0, createdAt: base),
            artifact(id: "b", runId: "run-1", sequence: nil, createdAt: base),   // mid-flight
            artifact(id: "c", runId: nil, sequence: 3, createdAt: base),         // legacy
            artifact(id: "d", runId: "", sequence: nil, createdAt: base),        // empty
            artifact(id: "e", runId: "   ", sequence: 1, createdAt: base),       // whitespace
            artifact(id: "f", runId: "run-2", sequence: 9, createdAt: base)
        ]

        let landed = ArtifactRunGrouping.groups(from: items).flatMap(\.artifacts).map(\.id)

        XCTAssertEqual(
            Set(landed), Set(items.map(\.id)),
            "an artifact that reaches no section is invisible while perfectly saved"
        )
        XCTAssertEqual(
            landed.count, items.count,
            "and none may be duplicated into two sections either"
        )
    }

    /// The regrouping step itself: the same artifact before and after its
    /// `runId` lands must be present BOTH times. Vanishing between two renders
    /// is the reported symptom, so both renders are asserted rather than the
    /// end state alone.
    func testAnArtifactSurvivesGainingItsRunIdInASecondUpdate() {
        let before = artifact(id: "new", runId: nil, sequence: nil, createdAt: base)
        let after = artifact(id: "new", runId: "run-1", sequence: 0, createdAt: base)

        for items in [[before], [after]] {
            let landed = ArtifactRunGrouping.groups(from: items).flatMap(\.artifacts).map(\.id)
            XCTAssertEqual(landed, ["new"], "present before and after the regroup")
        }
    }

    /// And the counter is not vacuous: a grouping that returned nothing would
    /// pass a "no duplicates" check trivially.
    func testTheTotalityCheckWouldNoticeADroppedArtifact() {
        let items = [artifact(id: "only", runId: "run-1", sequence: 0, createdAt: base)]

        XCTAssertEqual(ArtifactRunGrouping.groups(from: items).flatMap(\.artifacts).count, 1)
    }
}
