@testable import Fichero
import XCTest

/// #4308 (workspace half) + #4335 — workspaces are first-class sidebar nodes.
/// #4705 "5a"/#4812 (2026-09-18): the "opens the Research surface" half of
/// this is RETIRED — a workspace is an ordinary folder `Document`
/// (`isWorkspace: Bool` is a marker, not a different routing kind); the
/// sidebar already shows it wherever its parent is visible, with its own
/// icon, and selecting/creating one now behaves exactly like any folder.
/// The "opens Research" need moved to 5b/5c (a research PROJECT's own
/// chat/tasks/browser rendition — a `ResearchProject`, a different model
/// with no folder/Document link at all).
///
/// A workspace is a folder document with `is_workspace=true` (the engine's
/// `PATCH /{doc_id}/workspace` seam). Creation flows through the + menu
/// (`ItemTypeRegistry.createWorkspace` → `SidebarView.createNewWorkspace`),
/// REUSES `handleCreateNewFolder`'s own placement contract (Finder
/// semantics, #4121: nest into the selected folder, library root as the
/// fallback), inserts the node in the CURRENT library, and selects it.
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

    /// #4705 "5a"/#4812: selecting a workspace node no longer diverts to the
    /// Research surface — no special `isWorkspace` branch survives in
    /// `routeDocumentSelection` at all; a workspace document falls through
    /// to the SAME generic library branch every other document/folder gets.
    func testWorkspaceSelectionNoLongerDivertsToResearch() throws {
        let source = try appSource("Views/Sidebar/Sections/SidebarView+SelectionHandling.swift")
        XCTAssertFalse(
            source.contains("if doc.isWorkspace {"),
            "#4812: a workspace is an ordinary folder now — no dedicated routing branch"
        )
        XCTAssertFalse(
            source.contains("Routing workspace node"),
            "the retired branch's log line must not survive either"
        )
    }

    /// #4705 "5a"/#4812: creation REUSES `handleCreateNewFolder`'s placement
    /// contract (nest into the selected folder; library root as the
    /// fallback) via a `parentId` on `createWorkspace`, and selects the
    /// result without forcing `sidebarMode` — it browses like any folder
    /// (create → appear → select, never "→ Research").
    func testCreateNewWorkspaceReusesFolderPlacementAndSelects() throws {
        let source = try appSource("Views/Sidebar/Components/SidebarCreationHandlers.swift")
        XCTAssertTrue(source.contains("func createNewWorkspace()"))
        XCTAssertTrue(
            source.contains("libraryManager.getLibrary(id: windowState.libraryId)"),
            "creation targets the current window's library, falling back to global"
        )
        XCTAssertTrue(
            source.contains("documentStore.createWorkspace(name: \"New Workspace\", parentId: parentId)"),
            "placement must be a parameter on the SAME createWorkspace call, not a second code path"
        )
        XCTAssertTrue(
            source.contains("case .document(let doc) = selected.itemType, doc.docType == .folder"),
            "the parentId must come from the SAME selected-folder check handleCreateNewFolder uses"
        )
        XCTAssertTrue(source.contains("selectedItemId = \"doc:\\(workspace.id)\""))
        XCTAssertFalse(
            source.contains("sidebarMode = .research"),
            "#4812: creation must not force the Research takeover any more"
        )
    }

    /// The handler is actually wired into the registry at sidebar setup.
    func testRegistryWiringIncludesWorkspace() throws {
        let source = try appSource("Views/Sidebar/Components/SidebarObservers.swift")
        XCTAssertTrue(source.contains("itemRegistry.createWorkspace = createNewWorkspace"))
    }

    /// #4705 "5a": the redundant workspace-creation UI is gone from
    /// `ResearchProjectListView` — `createNewWorkspace()`/the registry above
    /// was already the real, wired create path.
    func testResearchProjectListViewHasNoWorkspaceUI() throws {
        let source = try appSource("Views/Chat/Research/ResearchProjectListView.swift")
        XCTAssertFalse(source.contains("workspacesSection"))
        XCTAssertFalse(source.contains("newWorkspaceForm"))
        XCTAssertFalse(source.contains("showingNewWorkspace"))
    }

    private func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
