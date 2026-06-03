@testable import Fichero
import Foundation
import XCTest

/// Tests for DocumentStoreTypes (request DTOs + error model) and
/// SidebarViewTypes (AppViewMode category routing + ActivityChildType
/// label/icon table + SelectedActivityRun.with helper).
final class DocumentStoreAndSidebarTypesTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    // MARK: - DocumentCreateRequest

    func testDocumentCreateRequestSnakeCase() throws {
        let req = DocumentCreateRequest(
            name: "report.pdf",
            parentId: "p-1",
            docType: .file,
            fileType: .pdf,
            path: "/tmp/report.pdf",
            pageContent: "body",
            metadata: ["tag": AnyCodable("x")]
        )
        let data = try JSONEncoder().encode(req)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertEqual(json?["name"] as? String, "report.pdf")
        XCTAssertEqual(json?["parent_id"] as? String, "p-1")
        XCTAssertEqual(json?["doc_type"] as? String, "file")
        XCTAssertEqual(json?["file_type"] as? String, "pdf")
        XCTAssertEqual(json?["page_content"] as? String, "body")
        XCTAssertNotNil(json?["metadata"])
    }

    func testDocumentCreateRequestDefaultsDocTypeToFile() throws {
        let req = DocumentCreateRequest(name: "untitled")
        XCTAssertEqual(req.docType, .file)
        XCTAssertNil(req.parentId)
        XCTAssertNil(req.fileType)
        XCTAssertTrue(req.metadata.isEmpty)
    }

    // MARK: - DocumentUpdateRequest

    func testDocumentUpdateRequestOmitsNilFields() throws {
        // Encoded JSON should include only the non-nil fields. Decoder
        // contract: backend interprets missing as "no change".
        var req = DocumentUpdateRequest()
        req.name = "renamed.pdf"
        let data = try JSONEncoder().encode(req)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertEqual(json?["name"] as? String, "renamed.pdf")
        XCTAssertNil(json?["parent_id"])
        XCTAssertNil(json?["doc_type"])
        XCTAssertNil(json?["file_type"])
        XCTAssertNil(json?["path"])
        XCTAssertNil(json?["page_content"])
        XCTAssertNil(json?["status"])
    }

    // MARK: - DocumentHierarchy

    func testHierarchyParentIsLastAncestor() {
        let root = makeDoc(id: "root", name: "Root")
        let mid = makeDoc(id: "mid", name: "Mid")
        let leaf = makeDoc(id: "leaf", name: "Leaf")
        let hierarchy = DocumentHierarchy(ancestors: [root, mid], document: leaf, children: [])
        XCTAssertEqual(hierarchy.parent?.id, "mid")
    }

    func testHierarchyParentNilForRoot() {
        let root = makeDoc(id: "root", name: "Root")
        let hierarchy = DocumentHierarchy(ancestors: [], document: root, children: [])
        XCTAssertNil(hierarchy.parent)
    }

    func testHierarchyBreadcrumbAppendsDocument() {
        let root = makeDoc(id: "root", name: "Root")
        let leaf = makeDoc(id: "leaf", name: "Leaf")
        let hierarchy = DocumentHierarchy(ancestors: [root], document: leaf, children: [])
        XCTAssertEqual(hierarchy.breadcrumb.map(\.id), ["root", "leaf"])
    }

    // MARK: - DocumentStoreError

    func testDocumentStoreErrorDescriptions() {
        XCTAssertEqual(DocumentStoreError.fileNotFound("/x").errorDescription, "File not found: /x")
        XCTAssertEqual(DocumentStoreError.fileNotReadable("/y").errorDescription, "Cannot read file: /y")
        XCTAssertEqual(DocumentStoreError.invalidFilename.errorDescription, "Invalid or empty filename")
        XCTAssertEqual(DocumentStoreError.invalidParentId.errorDescription, "Invalid parent folder ID")
        XCTAssertEqual(DocumentStoreError.invalidResponse.errorDescription, "Invalid server response")
        XCTAssertEqual(DocumentStoreError.badRequest.errorDescription, "Invalid request")
        XCTAssertEqual(DocumentStoreError.unauthorized.errorDescription, "Unauthorized access")
        XCTAssertEqual(DocumentStoreError.notFound.errorDescription, "Resource not found")
        XCTAssertEqual(DocumentStoreError.fileTooLarge.errorDescription, "File is too large to upload")
        XCTAssertEqual(DocumentStoreError.serverError(500).errorDescription, "Server error (HTTP 500)")
    }

    // MARK: - AppViewMode.category

    func testAppViewModeCategoryRouting() {
        // Locks the sidebar-to-toolbar wire: each AppViewMode collapses
        // into an ItemCategory used to decide which toolbar set renders.
        XCTAssertEqual(AppViewMode.library(nil).category, .folder)
        XCTAssertEqual(AppViewMode.search(nil).category, .search)
        XCTAssertEqual(AppViewMode.chat(nil).category, .chat)
        XCTAssertEqual(AppViewMode.comparison(nil).category, .chat)
        XCTAssertEqual(AppViewMode.workflow(nil).category, .workflow)
        XCTAssertEqual(AppViewMode.chain(nil).category, .workflow)
        XCTAssertEqual(AppViewMode.batches.category, .workflow)
        XCTAssertEqual(AppViewMode.batch(nil).category, .workflow)
        XCTAssertEqual(AppViewMode.automation.category, .workflow)
        XCTAssertEqual(AppViewMode.schedule(nil).category, .workflow)
        XCTAssertEqual(AppViewMode.trigger(nil).category, .workflow)
        XCTAssertEqual(AppViewMode.activity(nil).category, .workflow)
        XCTAssertEqual(AppViewMode.mindPalace.category, .folder)
    }

    func testEntitiesSidebarEntryPointRoutesToKnowledgeGraph() throws {
        let source = try Self.appSource("Views/Sidebar/SidebarView.swift")

        XCTAssertTrue(source.contains("id == \"entities-browser\""))
        XCTAssertTrue(source.contains("sidebarMode = .knowledgeGraph"))
    }

    func testEntitiesSidebarEntryPointIsPinnedAndFeatureGated() throws {
        let source = try Self.appSource("Views/Sidebar/SidebarView+ViewComponents.swift")

        XCTAssertTrue(source.contains("Label(\"Entities\", systemImage: SidebarMode.knowledgeGraph.icon)"))
        XCTAssertTrue(source.contains(".tag(\"entities-browser\")"))
        XCTAssertTrue(source.contains("FeatureManager.shared.isKnowledgeGraphEnabled"))
        XCTAssertTrue(source.contains("entitiesNavigationRow()"))
    }

    // MARK: - ActivityChildType

    func testActivityChildTypeRawValuesStable() {
        XCTAssertEqual(ActivityChildType.console.rawValue, "console")
        XCTAssertEqual(ActivityChildType.progress.rawValue, "progress")
        XCTAssertEqual(ActivityChildType.log.rawValue, "log")
    }

    func testActivityChildTypeAllCasesCount() {
        XCTAssertEqual(ActivityChildType.allCases.count, 3)
    }

    func testActivityChildTypeLabels() {
        let pairs: [(ActivityChildType, String)] = [
            (.console, "Console"), (.progress, "Progress"),
            (.log, "Log")
        ]
        for (kind, label) in pairs {
            XCTAssertEqual(kind.label, label, "kind=\(kind.rawValue)")
        }
    }

    func testActivityChildTypeIcons() {
        // SF Symbols — drift here breaks the Report Navigator sidebar.
        let pairs: [(ActivityChildType, String)] = [
            (.console, "text.alignleft"),
            (.progress, "chart.bar.fill"),
            (.log, "doc.text")
        ]
        for (kind, icon) in pairs {
            XCTAssertEqual(kind.icon, icon, "kind=\(kind.rawValue)")
        }
    }

    // MARK: - SelectedActivityRun.with(childType:)

    func testSelectedActivityRunWithReplacesChildType() {
        let original = SelectedActivityRun(
            id: "r-1", name: "Run", workflowId: "wf-1",
            threadId: "t-1", timestamp: Date(timeIntervalSince1970: 0),
            status: .running, isLive: true, childType: nil
        )
        let updated = original.with(childType: .progress)
        XCTAssertEqual(updated.id, original.id)
        XCTAssertEqual(updated.name, original.name)
        XCTAssertEqual(updated.workflowId, original.workflowId)
        XCTAssertEqual(updated.threadId, original.threadId)
        XCTAssertEqual(updated.timestamp, original.timestamp)
        XCTAssertEqual(updated.status, original.status)
        XCTAssertEqual(updated.isLive, original.isLive)
        XCTAssertEqual(updated.childType, .progress)
        XCTAssertNil(original.childType)  // immutability of original
    }

    func testSelectedActivityRunWithCanClearChildType() {
        let original = SelectedActivityRun(
            id: "r-1", name: "Run", workflowId: nil,
            threadId: nil, timestamp: Date(timeIntervalSince1970: 0),
            status: .completed, isLive: false, childType: .log
        )
        let cleared = original.with(childType: nil)
        XCTAssertNil(cleared.childType)
    }

    func testActivityRunStatusTypeRawValues() {
        XCTAssertEqual(SelectedActivityRun.ActivityRunStatusType.running.rawValue, "running")
        XCTAssertEqual(SelectedActivityRun.ActivityRunStatusType.completed.rawValue, "completed")
        XCTAssertEqual(SelectedActivityRun.ActivityRunStatusType.failed.rawValue, "failed")
        XCTAssertEqual(SelectedActivityRun.ActivityRunStatusType.cancelled.rawValue, "cancelled")
    }

    // MARK: - Helpers

    private func makeDoc(id: String, name: String) -> Document {
        Document(
            id: id, parentId: nil, docType: .folder,
            fileType: nil, name: name, path: nil,
            sequence: nil, bbox: nil, status: .completed,
            metadata: [:], pageContent: nil,
            createdAt: Date(), updatedAt: Date()
        )
    }
}
