//
//  WorkflowsFolderFromTheEngineTests.swift
//  FicheroTests
//
//  Daniel's sidebar, 2026-10-11: the top section read "Default Workflows" (locked) with no "Workflows". The engine
//  half was a library from before the Workflows folder never getting one (`heal_default_workflow_tree`, engine
//  test `test_heal_moves_a_root_default_workflows_into_workflows`). This is the app half, pinned with the engine's
//  own rows: `/roots` and `/system-workflows/view` exactly as the engine serialises them
//  for a project with Sources and the seeded presets, through the generated client, the real store and the real
//  tree builder. The row reads "Workflows", unlocked, with the workflow-folder look (2026-10-11), and the locked
//  Default Workflows inside.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class WorkflowsFolderMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var responses: [String: String] = [:]
    override static func canInit(with request: URLRequest) -> Bool {
        (request.url?.path ?? "").hasPrefix("/api/documents/")
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let path = request.url?.path ?? ""
        let json = Self.responses[path] ?? #"{"items": [], "count": 0, "withheld": 0}"#
        let response = HTTPURLResponse(
            url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

/// Rows serialised by the engine (`Document.model_dump_json(exclude_none=True)` for a project with Sources and the
/// seeded presets), unedited.
private enum EngineJSON {
    static let sources = """
    {"id": "src", "node_kind": "document", "doc_type": "folder", "name": "Sources", "metadata": {}, "attributes": {},
     "source_authority": "unknown", "is_workspace": false, "curated_items": [], "structure": [],
     "provenance_chain": [], "workflow_runs": [], "status": "pending", "is_read": false, "is_starred": false,
     "is_flagged": false, "exclude_from_processing": false, "exclude_from_search": false,
     "created_at": "2026-10-11T15:01:10.275363Z", "updated_at": "2026-10-11T15:01:10.275368Z", "sort_order": 0,
     "child_count": 0, "z_index": 0, "expected_thumbnail_path": "storage/thumbnails/sr/src.jpg",
     "expected_display_path": "storage/thumbnails/sr/src_display.jpg"}
    """

    static let workflows = """
    {"id": "system-workflows", "node_kind": "workflow_container", "doc_type": "folder", "name": "Workflows",
     "prototype_key": "folder", "metadata": {}, "attributes": {"scope": "global", "read_only": false, "system": true},
     "source_authority": "unknown", "is_workspace": false, "curated_items": [], "structure": [],
     "provenance_chain": [], "workflow_runs": [], "status": "pending", "is_read": false, "is_starred": false,
     "is_flagged": false, "exclude_from_processing": false, "exclude_from_search": false,
     "created_at": "2026-10-11T15:01:12.881242Z", "updated_at": "2026-10-11T15:01:12.881245Z", "sort_order": 0,
     "child_count": 1, "z_index": 0, "expected_thumbnail_path": "storage/thumbnails/sy/system-workflows.jpg",
     "expected_display_path": "storage/thumbnails/sy/system-workflows_display.jpg"}
    """

    static let defaultWorkflows = """
    {"id": "system-default-workflows", "parent_id": "system-workflows", "node_kind": "workflow_container",
     "doc_type": "folder", "name": "Default Workflows", "prototype_key": "folder", "metadata": {},
     "attributes": {"scope": "global", "read_only": true, "system": true}, "source_authority": "unknown",
     "is_workspace": false, "curated_items": [], "structure": [], "provenance_chain": [], "workflow_runs": [],
     "status": "pending", "is_read": false, "is_starred": false, "is_flagged": false, "exclude_from_processing": false,
     "exclude_from_search": false, "created_at": "2026-10-11T15:01:12.885497Z",
     "updated_at": "2026-10-11T15:01:12.885501Z", "sort_order": 0, "child_count": 1, "z_index": 0,
     "expected_thumbnail_path": "storage/thumbnails/sy/system-default-workflows.jpg",
     "expected_display_path": "storage/thumbnails/sy/system-default-workflows_display.jpg"}
    """

    /// `GET /api/documents/roots` (`list_roots`).
    static var roots: String { #"{"items": ["# + sources + ", " + workflows + #"], "count": 2, "withheld": 0}"# }

    /// `GET /api/documents/system-workflows/view?level=stored`, which the sidebar reads a folder's rows from.
    static var workflowsView: String {
        #"{"ancestors": [], "document": "# + workflows + #", "children": ["# + defaultWorkflows + "]}"
    }
}

@MainActor
@Suite(.serialized, .tags(.sidebar))
struct WorkflowsFolderFromTheEngineTests {
    @Test("the engine's roots draw Sources and Workflows; Workflows is an unlocked workflow folder holding the locked Default Workflows")
    func workflowsHoldsDefaultWorkflows() async throws {
        WorkflowsFolderMockURLProtocol.responses = [
            "/api/documents/roots": EngineJSON.roots,
            "/api/documents/system-workflows/view": EngineJSON.workflowsView
        ]
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [WorkflowsFolderMockURLProtocol.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://test.fichero")!,
            libraryPath: "/tmp/test.fichero",
            session: URLSession(configuration: configuration)
        )
        let store = DocumentStore(apiClient: APIClient(client: client))

        await store.loadCollections()
        #expect(store.collections.map(\.id) == ["src", "system-workflows"])
        let workflows = try #require(store.collections.first { $0.id == "system-workflows" })
        await store.cacheSidebarChildren(of: workflows)

        let tree = SidebarItemBuilder.buildLibraryHierarchy(from: store.sidebarDocuments, libraryId: UUID())
        let top = SidebarTopOrder.ordered(tree)
        #expect(top.map(\.name) == ["Sources", "Workflows"], "no top-level Default Workflows")

        let row = try #require(top.last)
        #expect(!row.isDefaultWorkflowFolder, "Workflows is not locked")
        // The workflow-folder look Default Workflows has, without its lock (Daniel, 2026-10-11).
        #expect(row.icon == "folder.badge.gearshape", "the workflow-folder icon")
        guard case .document(let doc) = row.itemType else { Issue.record("a document row"); return }
        #expect(doc.isWorkflowsFolder && doc.usesWorkflowTint, "purple, as Default Workflows")
        #expect(!doc.isReadOnly && !doc.isLockedSystemNode && doc.acceptsItemDrops, "no lock: drops and rename work")

        let inside = try #require(row.children?.first)
        #expect(inside.name == "Default Workflows")
        #expect(inside.isDefaultWorkflowFolder, "Default Workflows inside it is locked")
    }
}
