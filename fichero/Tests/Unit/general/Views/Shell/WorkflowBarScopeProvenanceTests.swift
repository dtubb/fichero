@testable import Fichero
import XCTest

/// The subject chip's menu names the document's ACTUAL artifacts, each with
/// the provenance that tells one pass from another (Daniel, 2026-09-03: "when
/// I try to choose what artifact to run on in the workflow bar, it's hard to
/// tell — if there are multiple regions — which model produced it"). Bare
/// by-TYPE rows survive only where the document has nothing of that type yet.
@MainActor
final class WorkflowBarScopeProvenanceTests: XCTestCase {

    /// A fixed "now" so the relative half of a label is deterministic.
    private let now = Date(timeIntervalSince1970: 1_756_900_000)

    private func choice(
        _ id: String,
        type: String,
        provider: String? = nil,
        model: String? = nil,
        stepName: String? = nil,
        minutesAgo: Double = 0
    ) -> WorkflowBarPolicy.ArtifactChoice {
        WorkflowBarPolicy.ArtifactChoice(
            id: id,
            artifactType: type,
            displayName: nil,
            provider: provider,
            model: model,
            stepName: stepName,
            createdAt: now.addingTimeInterval(-minutesAgo * 60)
        )
    }

    private func snapshot(
        artifacts: [WorkflowBarPolicy.ArtifactChoice],
        artifactId: String? = nil
    ) -> WorkflowBarPolicy.SelectionSnapshot {
        WorkflowBarPolicy.SelectionSnapshot(
            artifactId: artifactId,
            artifactDocumentId: artifactId == nil ? nil : "page-1",
            detailDocumentId: "page-1",
            detailDocumentName: "Hoja",
            detailArtifacts: artifacts
        )
    }

    private func options(
        _ artifacts: [WorkflowBarPolicy.ArtifactChoice],
        artifactId: String? = nil
    ) -> [WorkflowBarPolicy.ScopeOption] {
        WorkflowBarPolicy.scopeMenuOptions(
            from: snapshot(artifacts: artifacts, artifactId: artifactId), now: now
        )
    }

    // MARK: - 0 / 1 / many

    func testTypeWithNoArtifactsKeepsItsBareRow() {
        // `artifacts_source` resolves when the run starts, so aiming at a
        // type the document has none of yet is still a real choice.
        let rows = options([])
        XCTAssertTrue(rows.contains {
            $0.id == "artifact-type-translation" && $0.label == "Translation of Hoja"
        })
    }

    func testSingleArtifactReplacesTheBareTypeRowWithProvenance() {
        let rows = options([choice("a1", type: "transcription", model: "gemini-2.5-flash")])
        XCTAssertFalse(rows.contains { $0.id == "artifact-type-transcription" })
        guard let row = rows.first(where: { $0.id == "artifact-a1" }) else {
            return XCTFail("expected a row for the one transcription")
        }
        XCTAssertTrue(
            row.label.hasPrefix("Transcription — gemini-2.5-flash,"),
            "label was \(row.label)"
        )
        guard case .artifact(_, let artifactId, _, _, let type, _)? = row.scope else {
            return XCTFail("expected an artifact scope")
        }
        XCTAssertEqual(artifactId, "a1")
        XCTAssertEqual(type, "transcription")
    }

    func testSeveralArtifactsOfOneTypeEachGetARowNewestFirst() {
        let rows = options([
            choice("old", type: "transcription", model: "qwen/qwen2.5-vl", minutesAgo: 90),
            choice("new", type: "transcription", model: "gemini-2.5-flash", minutesAgo: 5),
            choice("mid", type: "transcription", provider: "apple_vision", minutesAgo: 40)
        ])
        let ids = rows.map(\.id).filter { $0.hasPrefix("artifact-") && !$0.hasPrefix("artifact-type-") }
        XCTAssertEqual(ids, ["artifact-new", "artifact-mid", "artifact-old"])
        // The model id is shortened the way the model chip shortens it, and a
        // provider-only artifact is named by its provider, not by a guess.
        XCTAssertTrue(rows.contains { $0.label.hasPrefix("Transcription — qwen2.5-vl,") })
        XCTAssertTrue(rows.contains { $0.label.hasPrefix("Transcription — Apple Vision,") })
    }

    // MARK: - Honest labels

    func testArtifactWithNoRecordedProducerSaysSo() {
        let rows = options([choice("a1", type: "transcription")])
        XCTAssertTrue(
            rows.contains { $0.label.hasPrefix("Transcription — unknown model,") },
            "expected an honest label, got \(rows.map(\.label))"
        )
    }

    func testTypeTheClientDoesNotEnumerateStillGetsItsArtifacts() {
        // "Regions" is not in the artifacts_source vocabulary, but a document
        // that HAS them must still be able to aim at one.
        let rows = options([
            choice("r1", type: "regions", provider: "apple_vision"),
            choice("r2", type: "regions", model: "qwen/qwen2.5-vl", minutesAgo: 10)
        ])
        XCTAssertTrue(rows.contains { $0.id == "artifact-r1" })
        XCTAssertTrue(rows.contains { $0.id == "artifact-r2" })
        XCTAssertTrue(rows.contains { $0.label.hasPrefix("Regions — Apple Vision,") })
    }

    // MARK: - Shape

    func testFocusedArtifactIsNamedOnceNotTwice() {
        let rows = options(
            [choice("a1", type: "transcription", model: "gemini-2.5-flash")],
            artifactId: "a1"
        )
        XCTAssertTrue(rows.contains { $0.id == "artifact" })
        XCTAssertFalse(rows.contains { $0.id == "artifact-a1" })
        // The rung itself carries the provenance, so "the focused one" says
        // WHICH one.
        XCTAssertEqual(
            rows.first { $0.id == "artifact" }.map { $0.label.hasPrefix("Transcription — gemini") },
            true
        )
    }

    func testALongArtifactListCollapsesIntoSubmenusPerType() {
        let many = (1...10).map {
            choice("t\($0)", type: "transcription", model: "m\($0)", minutesAgo: Double($0))
        }
        let rows = options(many)
        guard let parent = rows.first(where: { $0.id == "artifact-type-transcription" }) else {
            return XCTFail("expected the type row to become a submenu")
        }
        XCTAssertEqual(parent.children.count, 10)
        XCTAssertEqual(parent.children.first?.id, "artifact-t1")
        // The parent still aims by TYPE, so picking it is meaningful on its own.
        guard case .artifact(_, let artifactId, _, _, let type, _)? = parent.scope else {
            return XCTFail("expected an artifact scope on the parent row")
        }
        XCTAssertNil(artifactId)
        XCTAssertEqual(type, "transcription")
        // Nothing was lost: no artifact row is left dangling at the top level.
        XCTAssertFalse(rows.contains {
            $0.id.hasPrefix("artifact-t") && !$0.id.hasPrefix("artifact-type-")
        })
    }

    func testShortListStaysFlat() {
        let rows = options([
            choice("a1", type: "transcription", model: "m1"),
            choice("a2", type: "transcription", model: "m2", minutesAgo: 3)
        ])
        XCTAssertTrue(rows.allSatisfy { $0.children.isEmpty })
        XCTAssertTrue(rows.contains { $0.id == "artifact-a1" })
        XCTAssertTrue(rows.contains { $0.id == "artifact-a2" })
    }

    // MARK: - Duplicate passes

    func testIdenticalRowsGrowAShortIdTailAndOthersDoNot() {
        // Cached Detect Regions re-runs mint duplicates: same model, same
        // minute. Without a tail the menu offers the same row three times.
        let same = now.addingTimeInterval(-30)
        let rows = options([
            WorkflowBarPolicy.ArtifactChoice(
                id: "6f2a1b9c-0000-4000-8000-000000000001", artifactType: "regions",
                provider: "apple_vision", createdAt: same
            ),
            WorkflowBarPolicy.ArtifactChoice(
                id: "8d4e7c3a-0000-4000-8000-000000000002", artifactType: "regions",
                provider: "apple_vision", createdAt: same
            ),
            choice("solo", type: "transcription", model: "gemini-2.5-flash")
        ])
        let regionLabels = rows.filter { $0.id.hasPrefix("artifact-6") || $0.id.hasPrefix("artifact-8") }
            .map(\.label)
        XCTAssertEqual(regionLabels.count, 2)
        XCTAssertEqual(Set(regionLabels).count, 2, "duplicates must be tellable apart: \(regionLabels)")
        XCTAssertTrue(regionLabels.contains { $0.hasSuffix(" · 6f2a1b") })
        XCTAssertTrue(regionLabels.contains { $0.hasSuffix(" · 8d4e7c") })
        // A row with no twin stays clean.
        XCTAssertEqual(
            rows.first { $0.id == "artifact-solo" }.map { $0.label.contains(" · ") },
            false
        )
    }

    // MARK: - "Run Workflow on This"

    func testPinnedArtifactOutranksABrowserMultiSelect() {
        // The multi-select guard exists to stop a LINGERING artifact focus
        // from stealing the bar; an explicit aim from the inspector is the
        // opposite of lingering, so it wins.
        var snap = snapshot(artifacts: [], artifactId: "a1")
        snap.browserSelection = ["d1", "d2", "d3"]
        snap.artifactPinned = true
        guard case .artifact(_, let artifactId, _, _, _, _) =
                WorkflowBarPolicy.resolveRunScope(snap) else {
            return XCTFail("a pinned artifact must survive a multi-select")
        }
        XCTAssertEqual(artifactId, "a1")
    }

    func testUnpinnedArtifactStillYieldsToABrowserMultiSelect() {
        var snap = snapshot(artifacts: [], artifactId: "a1")
        snap.browserSelection = ["d1", "d2", "d3"]
        XCTAssertEqual(
            WorkflowBarPolicy.resolveRunScope(snap),
            .documents(ids: ["d1", "d2", "d3"])
        )
    }

    func testAutomaticStaysFirstAndTheLadderRungsSurvive() {
        let rows = options([choice("a1", type: "transcription", model: "m1")])
        XCTAssertEqual(rows.first?.id, "automatic")
        XCTAssertNil(rows.first?.scope)
        XCTAssertTrue(rows.contains { $0.id == "detail" && $0.label == "Hoja" })
    }
}
