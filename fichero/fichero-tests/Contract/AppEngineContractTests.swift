//
//  AppEngineContractTests.swift
//  FicheroTests
//
//  Live app<->engine contract tests. The Swift mirror of the Python contract
//  walker: drive the real Swift service layer against a *running* engine
//  serving a freshly seeded, disposable library, and assert the app sees
//  exactly the data the library holds.
//
//  Nothing is hard-coded: every expectation comes from the seeder
//  (seed_test_library.py), which reads its counts back from the library
//  (ground truth) and emits the seeded row ids by name. So the comparison is
//  "engine-over-HTTP == library ground truth" — which proves the API/envelope
//  layer (and the hand-written Swift service wrappers) faithfully expose what
//  the engine stores. This is the layer #1075 broke silently.
//
//  Engine lifecycle is handled by EngineHarness: reuse a running engine if
//  present, else spawn one against an isolated base path. Skips (not fails) if
//  no engine can be reached or spawned (e.g. CI without the Python venv).
//

import XCTest

@testable import Fichero
import FicheroAPIClient

@MainActor
final class AppEngineContractTests: XCTestCase {
    private var engine: EngineHarness.LiveEngine!

    override func setUp() async throws {
        try await super.setUp()
        do {
            engine = try await EngineHarness.live()
        } catch {
            throw XCTSkip("Live engine unavailable (\(error)) — skipping app<->engine contract tests.")
        }
    }

    private func expected(_ key: String) throws -> Int {
        try XCTUnwrap(engine.expected[key], "seeder did not report expected['\(key)']")
    }

    private func seededID(_ key: String) throws -> String {
        try XCTUnwrap(engine.ids[key], "seeder did not report id '\(key)'")
    }

    // MARK: - Reads round-trip (engine HTTP == library ground truth)

    func test_documents_match_library() async throws {
        let svc = DocumentService(ficheroClient: engine.client)

        let collections = try await svc.getCollections()
        XCTAssertEqual(collections.count, try expected("collections"), "collections via /documents/collections")

        let children = try await svc.getChildren(try seededID("collection"))
        XCTAssertEqual(children.count, try expected("children_of_collection"), "children of seeded collection")
    }

    func test_workflows_match_library() async throws {
        let svc = WorkflowService(ficheroClient: engine.client)
        let workflows = try await svc.listWorkflows()
        XCTAssertEqual(workflows.count, try expected("workflows"), "workflows via /workflows")
    }

    func test_artifacts_match_library() async throws {
        let svc = ArtifactService(ficheroClient: engine.client)
        let artifacts = try await svc.getArtifacts(forDocumentId: try seededID("doc_letter"))
        XCTAssertEqual(artifacts.count, try expected("artifacts_for_letter"), "artifacts on seeded letter doc")
    }

    /// Entities have no hand-written service — go straight through the
    /// generated client, which also proves the envelope unwraps to typed rows.
    func test_entities_envelope_matches_library() async throws {
        let response = try await engine.client.api.listEntitiesApiEntitiesGet(.init())
        switch response {
        case .ok(let okResponse):
            let items = try okResponse.body.json.items
            XCTAssertEqual(items.count, try expected("entities"), "entities via /entities envelope")
        default:
            XCTFail("unexpected /entities response: \(response)")
        }
    }

    // MARK: - Write round-trip (exercises the live create/read/delete path)

    func test_create_read_delete_round_trip() async throws {
        let svc = DocumentService(ficheroClient: engine.client)
        let name = "itest-write-\(UUID().uuidString.prefix(8))"

        let created = try await svc.createCollection(name: name)
        XCTAssertEqual(created.name, name, "created collection name round-trips")

        let fetched = try await svc.getDocument(created.id)
        XCTAssertEqual(fetched.id, created.id, "fetched id matches created")
        XCTAssertEqual(fetched.name, name, "fetched name matches created")

        // Clean up so read-count tests stay correct regardless of order.
        try await svc.deleteDocument(created.id)
    }
}
