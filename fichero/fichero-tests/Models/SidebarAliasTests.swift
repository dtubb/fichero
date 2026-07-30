@testable import Fichero
import Foundation
import XCTest

/// Locks the client side of Finder-style alias support (#2591): the Document
/// model decodes the engine's alias fields, alias rows get the alias badge,
/// selection resolves to the target, and Make Alias creates real engine
/// alias nodes — never sidebar-only copies.
final class SidebarAliasTests: XCTestCase {

    func testIsAliasRequiresKindAndTarget() {
        XCTAssertTrue(
            Document(name: "a", nodeKind: "alias", aliasTargetId: "t-1").isAlias
        )
        XCTAssertFalse(Document(name: "plain").isAlias)
        // Kind without a target is dangling-at-birth — not a working alias.
        XCTAssertFalse(Document(name: "a", nodeKind: "alias").isAlias)
        XCTAssertFalse(Document(name: "a", aliasTargetId: "t-1").isAlias)
    }

    func testDocumentDecodesEngineAliasFields() throws {
        let json = """
        {"id": "b-1", "doc_type": "file", "name": "Paper alias",
         "status": "pending", "metadata": {},
         "node_kind": "alias", "alias_target_id": "doc-9",
         "created_at": "2026-07-26T00:00:00Z", "updated_at": "2026-07-26T00:00:00Z"}
        """
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let doc = try decoder.decode(Document.self, from: Data(json.utf8))
        XCTAssertEqual(doc.nodeKind, "alias")
        XCTAssertEqual(doc.aliasTargetId, "doc-9")
        XCTAssertTrue(doc.isAlias)
    }

    func testAliasRowsCarryTheAliasBadgeAndMenu() throws {
        let label = try appSource("Views/Sidebar/ItemRow/SidebarItemRow+Label.swift")
        // Badge precedence: the alias arrow wins over ingest badges.
        XCTAssertTrue(label.contains("if doc.isAlias {"))

        let menu = try appSource("Views/Sidebar/ItemRow/SidebarItemContextMenu.swift")
        XCTAssertTrue(menu.contains(#"Label("Make Alias", systemImage: "arrowshape.turn.up.right")"#))
        XCTAssertTrue(menu.contains("if let onMakeAlias, case .document = item.itemType {"))
    }

    func testSelectionResolvesAliasesViaBackendFetch() throws {
        let routing = try appSource("Views/Sidebar/Sections/SidebarView+SelectionHandling.swift")
        // Aliases route through the resolver (backend fetch — lazy caches
        // can't prove danglingness), and dangling surfaces the alert. The
        // branch lives inside the consolidated routeDocumentSelection seam
        // since #4335's routing unification.
        XCTAssertTrue(routing.contains("routeDocumentSelection"))
        XCTAssertTrue(routing.contains("doc.isAlias"))
        XCTAssertTrue(routing.contains("library.documentService.getDocument(targetId)"))
        XCTAssertTrue(routing.contains("sidebarState.aliasErrorMessage"))
    }

    func testMakeAliasUsesRealEngineAliasNodes() throws {
        let row = try appSource("Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift")
        XCTAssertTrue(row.contains("library.bookmarkService.createBookmark("))
        XCTAssertTrue(row.contains("parentId: doc.parentId"))
    }

    private func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
