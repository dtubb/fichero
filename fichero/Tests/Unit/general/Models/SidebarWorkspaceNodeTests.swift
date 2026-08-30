@testable import Fichero
import XCTest

/// #4308 (workspace half) + #4335 — workspaces are first-class sidebar nodes.
///
/// A workspace is a folder document with `is_workspace=true` (the engine's
/// `PATCH /{doc_id}/workspace` seam). Creation now flows through the + menu
/// (`ItemTypeRegistry.createWorkspace` → `SidebarView.createNewWorkspace`),
/// inserts the node in the CURRENT library, selects it, and opens the
/// Research surface; selecting a workspace row routes there too.
@MainActor
final class SidebarWorkspaceNodeTests: XCTestCase {

    private func makeWorkspaceDoc(id: String = "ws-1", name: String = "Field Notes") -> Document {
        Document(id: id, parentId: nil, docType: .folder, name: name, isWorkspace: true)
    }

    // MARK: - Tree presentation

    /// Workspace rows read as workspaces, not plain folders — one typed node
    /// vocabulary in the tree (#4335).
    func testWorkspaceDocGetsTheWorkspaceIcon() {
        let item = SidebarItem.fromDocument(makeWorkspaceDoc(), libraryId: UUID())
        XCTAssertEqual(item.icon, "square.grid.2x2")
        XCTAssertTrue(item.isFolder, "a workspace is still a container node")
    }

    /// A plain folder keeps the folder glyph — the workspace icon must not leak.
    func testPlainFolderKeepsFolderIcon() {
        let folder = Document(id: "f-1", docType: .folder, name: "Letters")
        XCTAssertEqual(SidebarItem.fromDocument(folder, libraryId: UUID()).icon, DocType.folder.icon)
    }

    /// Workspace folders are sidebar-visible like any container.
    func testWorkspaceDocIsSidebarVisible() {
        XCTAssertTrue(SidebarItemBuilder.isSidebarVisible(makeWorkspaceDoc()))
    }

    // MARK: - Creation registry

    /// The + menu offers Workspace (AI group) once the handler is injected —
    /// the ONE source of truth every creation surface shares (#4121).
    func testRegistryOffersWorkspaceWhenHandlerInjected() {
        let registry = ItemTypeRegistry()
        XCTAssertFalse(registry.definitions.contains { $0.id == "workspace" })

        registry.createWorkspace = {}
        let definition = registry.definitions.first { $0.id == "workspace" }
        XCTAssertNotNil(definition)
        XCTAssertEqual(definition?.menuCategory, .aiTools)
        XCTAssertEqual(definition?.icon, "square.grid.2x2")
    }

    // MARK: - Routing + creation seams (source contract)

    /// Selecting a workspace node opens the Research surface, never the plain
    /// folder browse — and the case must precede the generic document case.
    func testWorkspaceSelectionRoutesToResearchSurface() throws {
        let source = try appSource("Views/Sidebar/Sections/SidebarView+SelectionHandling.swift")
        let workspaceBranch = source.range(of: "if doc.isWorkspace {")
        let libraryFallback = source.range(of: "viewMode = .library(doc)")
        XCTAssertNotNil(workspaceBranch, "#4308: workspace rows need their own routing branch")
        if let workspaceBranch, let libraryFallback {
            XCTAssertTrue(workspaceBranch.lowerBound < libraryFallback.lowerBound)
        }
        XCTAssertTrue(source.contains("sidebarMode = .research"))
    }

    /// Creation inserts in the CURRENT window's library, selects the node, and
    /// opens Research (#4335: create → appear → select).
    func testCreateNewWorkspaceTargetsCurrentLibraryAndSelects() throws {
        let source = try appSource("Views/Sidebar/Components/SidebarCreationHandlers.swift")
        XCTAssertTrue(source.contains("func createNewWorkspace()"))
        XCTAssertTrue(
            source.contains("libraryManager.getLibrary(id: windowState.libraryId)"),
            "creation targets the current window's library, falling back to global"
        )
        XCTAssertTrue(source.contains("documentStore.createWorkspace(name:"))
        XCTAssertTrue(source.contains("selectedItemId = \"doc:\\(workspace.id)\""))
        XCTAssertTrue(source.contains("sidebarMode = .research"))
    }

    /// The handler is actually wired into the registry at sidebar setup.
    func testRegistryWiringIncludesWorkspace() throws {
        let source = try appSource("Views/Sidebar/Components/SidebarObservers.swift")
        XCTAssertTrue(source.contains("itemRegistry.createWorkspace = createNewWorkspace"))
    }

    private func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
