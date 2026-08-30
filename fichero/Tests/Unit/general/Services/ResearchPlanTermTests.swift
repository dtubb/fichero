@testable import Fichero
import FicheroAPIClient
import XCTest

/// #1729 — the backend's research plan agent shipped behind an optional `term`
/// on `POST /api/research/plans`, but the Swift wrapper never sent the field,
/// so the AI assist was unreachable from the app. These cover the two seams
/// that made it invisible: the request the wrapper constructs, and the plan
/// metadata the response carries back.
@MainActor
final class ResearchPlanTermTests: XCTestCase {

    // MARK: - Request construction

    /// The whole bug: `term` must land on the OpenAPI-typed field. A declared
    /// field routed through `additionalProperties` round-trips on the wire and
    /// is then dropped by the Pydantic model — a silently blank plan.
    func testRequestCarriesTheResearchTermOnTheTypedField() {
        let request = ResearchService.planCreateRequest(
            projectId: "proj-1",
            name: "Marshall diaries",
            term: "Marshall diaries"
        )
        XCTAssertEqual(request.term, "Marshall diaries")
        XCTAssertEqual(request.projectId, "proj-1")
        XCTAssertEqual(request.name, "Marshall diaries")
    }

    func testRequestOmitsTermWhenNoneIsSupplied() {
        let request = ResearchService.planCreateRequest(projectId: "proj-1", name: "Plan 1")
        XCTAssertNil(request.term, "A hand-made plan must not trigger the plan agent.")
    }

    /// A whitespace-only term would run the agent on nothing.
    func testRequestTreatsBlankTermAsAbsent() {
        for blank in ["", "   ", "\n\t "] {
            let request = ResearchService.planCreateRequest(
                projectId: "proj-1", name: "Plan 1", term: blank
            )
            XCTAssertNil(request.term, "Blank term \(blank.debugDescription) must be omitted")
        }
    }

    func testRequestTrimsTheTerm() {
        let request = ResearchService.planCreateRequest(
            projectId: "proj-1", name: "Plan 1", term: "  Chocó archives \n"
        )
        XCTAssertEqual(request.term, "Chocó archives")
    }

    func testRequestPreservesDescription() {
        let request = ResearchService.planCreateRequest(
            projectId: "proj-1", name: "Plan 1", description: "notes", term: "gold mining"
        )
        XCTAssertEqual(request.description, "notes")
        XCTAssertEqual(request.term, "gold mining")
    }

    // MARK: - Response metadata

    /// The backend shape from `create_plan_impl`: the agent payload lands under
    /// `metadata["research_plan"]`, the term under `metadata["research_term"]`.
    func testPlanDecodesTheAgentBriefFromMetadata() throws {
        let plan = try Self.decodePlan(metadata: """
        {
          "research_term": "Marshall diaries",
          "research_plan": {
            "archives": ["National Archives", "Kew"],
            "locations": ["London"],
            "multilingual_terms": {"es": ["diarios"], "en": ["diaries"]},
            "summary": "Start with the state papers."
          }
        }
        """)
        let brief = try XCTUnwrap(plan.brief)
        XCTAssertEqual(plan.metadata?.researchTerm, "Marshall diaries")
        XCTAssertEqual(brief.archives, ["National Archives", "Kew"])
        XCTAssertEqual(brief.locations, ["London"])
        XCTAssertEqual(brief.summary, "Start with the state papers.")
        XCTAssertEqual(brief.multilingualTerms["es"], ["diarios"])
    }

    /// Dictionaries have no order; the rendered list must not shuffle.
    func testMultilingualTermsRenderInAStableLanguageOrder() {
        let brief = ResearchPlanBrief(multilingualTerms: ["fr": ["dossiers"], "en": ["records"], "es": ["registros"]])
        XCTAssertEqual(brief.sortedMultilingualTerms.map(\.language), ["en", "es", "fr"])
    }

    func testHandMadePlanHasNoBrief() throws {
        let plan = try Self.decodePlan(metadata: "{}")
        XCTAssertNil(plan.brief)
    }

    func testPlanWithoutMetadataStillDecodes() throws {
        let plan = try Self.decodePlan(metadata: nil)
        XCTAssertNil(plan.metadata)
        XCTAssertNil(plan.brief)
        XCTAssertEqual(plan.id, "plan-1")
    }

    /// An empty agent payload is not worth a section of chrome.
    func testEmptyBriefIsNotRendered() throws {
        let plan = try Self.decodePlan(metadata: #"{"research_plan": {"archives": [], "locations": [], "multilingual_terms": {}, "summary": ""}}"#)
        XCTAssertNil(plan.brief)
    }

    /// The brief is LLM-shaped advisory data. A field the agent got wrong must
    /// not fail the plan decode and hide the plan from the list entirely.
    func testMalformedAgentPayloadDegradesInsteadOfHidingThePlan() throws {
        let plan = try Self.decodePlan(metadata: #"{"research_plan": {"archives": "Kew", "summary": "ok"}}"#)
        XCTAssertEqual(plan.id, "plan-1")
        XCTAssertEqual(plan.brief?.summary, "ok")
        XCTAssertEqual(plan.brief?.archives, [])
    }

    func testUnrecognisedMetadataShapeDoesNotFailThePlanDecode() throws {
        let plan = try Self.decodePlan(metadata: #"{"research_plan": "not an object", "other": 3}"#)
        XCTAssertEqual(plan.id, "plan-1")
        XCTAssertNil(plan.brief)
    }

    // MARK: - Helpers

    private static func decodePlan(metadata: String?) throws -> ResearchPlan {
        let metadataField = metadata.map { ", \"metadata\": \($0)" } ?? ""
        let json = """
        {
          "id": "plan-1",
          "project_id": "proj-1",
          "name": "Plan 1",
          "description": "",
          "status": "draft",
          "order_index": 0,
          "created_at": "2026-07-30T00:00:00Z",
          "updated_at": "2026-07-30T00:00:00Z"\(metadataField)
        }
        """
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(ResearchPlan.self, from: Data(json.utf8))
    }
}
