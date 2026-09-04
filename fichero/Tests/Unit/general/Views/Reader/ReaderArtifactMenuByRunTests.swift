@testable import Fichero
import XCTest

/// The reader's "Showing" submenu lists artifacts BY RUN (Daniel, 2026-09-04:
/// "sub-artifacts ought to be by RUN, no?"). The flat list it replaced named
/// five rows "Transcription_Review — anthropic/claude-sonnet-5" with no time,
/// no run, and no way to tell tonight's three reviews from last week's.
@MainActor
final class ReaderArtifactMenuByRunTests: XCTestCase {

    /// A fixed "now" so the time half of every label is deterministic.
    private let now = Date(timeIntervalSince1970: 1_756_900_000)

    private func artifact(
        _ id: String,
        type: String = "transcription_review",
        runId: String? = nil,
        workflowId: String? = nil,
        sequence: Int? = nil,
        model: String? = nil,
        provider: String? = nil,
        stepName: String? = nil,
        minutesAgo: Double = 0
    ) -> Artifact {
        Artifact(
            id: id,
            documentId: "page-1",
            artifactType: type,
            runId: runId,
            provider: provider,
            model: model,
            stepName: stepName,
            workflowId: workflowId,
            sequence: sequence,
            createdAt: now.addingTimeInterval(-minutesAgo * 60)
        )
    }

    // MARK: - Grouping

    func testArtifactsGroupByRunNewestFirst() {
        let groups = ReaderArtifactMenu.groups(
            from: [
                artifact("a", runId: "run-old", sequence: 0, minutesAgo: 600),
                artifact("b", runId: "run-new", sequence: 0, minutesAgo: 1),
                artifact("c", runId: "run-new", sequence: 1, minutesAgo: 1)
            ],
            now: now
        )
        XCTAssertEqual(groups.map(\.id), ["run-new", "run-old"])
        XCTAssertEqual(
            groups.first?.choices.map(\.artifactId), ["b", "c"],
            "Within a run, rows follow pipeline sequence — the same order the artifact browser uses."
        )
    }

    func testNewestRunIsMarkedLatest() {
        let groups = ReaderArtifactMenu.groups(
            from: [
                artifact("a", runId: "run-old", minutesAgo: 600),
                artifact("b", runId: "run-new", minutesAgo: 1)
            ],
            now: now
        )
        XCTAssertEqual(groups.map(\.isLatest), [true, false])
        XCTAssertTrue(
            groups[0].header.contains("(latest)"),
            "The pass you just ran has to be the obvious one — that was the whole complaint."
        )
        XCTAssertFalse(groups[1].header.contains("(latest)"))
    }

    func testUngroupedArtifactsCollapseIntoATrailingEarlierSection() {
        let groups = ReaderArtifactMenu.groups(
            from: [
                artifact("legacy", runId: nil, minutesAgo: 5),
                artifact("b", runId: "run-new", minutesAgo: 90)
            ],
            now: now
        )
        XCTAssertEqual(groups.map(\.id), ["run-new", "earlier"])
        XCTAssertEqual(groups.last?.title, "Earlier")
        XCTAssertEqual(
            groups.last?.time, "",
            "The Earlier section spans no single moment, so it claims none."
        )
        XCTAssertEqual(
            groups.flatMap(\.choices).count, 2,
            "Grouping never hides an artifact — every row lands in exactly one section."
        )
    }

    func testRunsBeyondTheCapAreDropped() {
        let many = (0..<12).map { index in
            artifact("a\(index)", runId: "run-\(index)", minutesAgo: Double(index))
        }
        let groups = ReaderArtifactMenu.groups(from: many, now: now)
        XCTAssertEqual(groups.count, ReaderArtifactMenu.maxRuns)
        XCTAssertEqual(
            groups.first?.id, "run-0",
            "The cap drops the OLDEST runs; the newest pass must never be the one cut."
        )
    }

    // MARK: - Headers

    func testRunHeaderNamesTheWorkflowAndWhenItRan() {
        let groups = ReaderArtifactMenu.groups(
            from: [artifact("a", runId: "run-1", workflowId: "wf-1", minutesAgo: 1)],
            workflowName: { $0 == "wf-1" ? "Paleographer Review" : nil },
            now: now
        )
        XCTAssertEqual(groups.first?.title, "Paleographer Review")
        XCTAssertTrue(groups[0].header.hasPrefix("Paleographer Review — "))
        XCTAssertTrue(
            groups[0].header.contains(WorkflowBarPolicy.provenanceTime(now.addingTimeInterval(-60), now: now)),
            "The header says WHEN the run wrote, in the same words the scope menu uses."
        )
    }

    func testRunHeaderFallsBackToTheStepThenToAnHonestGeneric() {
        let step = ReaderArtifactMenu.groups(
            from: [artifact("a", runId: "run-1", stepName: "r3", minutesAgo: 1)],
            now: now
        )
        XCTAssertEqual(step.first?.title, "r3")

        let generic = ReaderArtifactMenu.groups(
            from: [artifact("a", runId: "run-1", minutesAgo: 1)],
            now: now
        )
        XCTAssertEqual(
            generic.first?.title, "Workflow Run",
            "An unnamed run says so rather than borrowing a plausible name."
        )
    }

    // MARK: - Labels shared with the scope menu

    func testRowsAreLabelledByTheScopeMenusOwnRule() {
        let one = artifact("a", runId: "run-1", model: "anthropic/claude-sonnet-5", minutesAgo: 1)
        let groups = ReaderArtifactMenu.groups(from: [one], now: now)
        XCTAssertEqual(
            groups.first?.choices.first?.label,
            WorkflowBarPolicy.artifactChoiceLabel(ReaderArtifactMenu.choice(for: one), now: now),
            """
            The reader submenu and the workflow bar's scope menu name the same \
            artifact through ONE function, so the two menus can never disagree.
            """
        )
    }

    func testRowsCarryTheTimeThatTellsTwoPassesApart() {
        let groups = ReaderArtifactMenu.groups(
            from: [artifact("a", runId: "run-1", model: "gemini-flash-lite", minutesAgo: 1)],
            now: now
        )
        let label = groups.first?.choices.first?.label ?? ""
        XCTAssertTrue(
            label.contains(WorkflowBarPolicy.provenanceTime(now.addingTimeInterval(-60), now: now)),
            "A row with no timestamp cannot be told from the identical row beside it."
        )
    }

    func testIdenticalRowsGrowATailSoTheyCanBeToldApart() {
        let twins = [
            artifact("aaaaaaaa-1111", runId: "run-1", model: "gemini-flash-lite", minutesAgo: 1),
            artifact("bbbbbbbb-2222", runId: "run-1", model: "gemini-flash-lite", minutesAgo: 1)
        ]
        let labels = ReaderArtifactMenu.groups(from: twins, now: now)
            .flatMap(\.choices).map(\.label)
        XCTAssertEqual(Set(labels).count, 2, "Two rows reading identically are two rows you cannot choose between.")
    }

    func testFlattenedReturnsEveryRowInMenuOrder() {
        let groups = ReaderArtifactMenu.groups(
            from: [
                artifact("a", runId: "run-old", minutesAgo: 600),
                artifact("b", runId: "run-new", minutesAgo: 1)
            ],
            now: now
        )
        XCTAssertEqual(ReaderArtifactMenu.flattened(groups).map(\.artifactId), ["b", "a"])
    }
}
