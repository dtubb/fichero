@testable import Fichero
import Foundation
import Testing

/// `sidebar.project.click-selects-and-inspects` (#5422): clicking a project row selects it and
/// the Inspector shows the project. Driven through the real `SidebarSelectionState` (the store
/// the row's tap writes and its highlight reads) and the Inspector's routing rule.
struct ProjectRowInspectsTests {
    private let projectId = UUID(uuidString: "6F2A0A6E-2C2B-4B49-9E9B-000000000001")!

    @Test("a project click is the selection: the row highlights and the Inspector shows the project")
    func projectClickSelectsAndInspects() {
        // WHY: the bug was a project click that neither highlighted the row nor moved the
        // Inspector; the highlight reads `selectedDestinations`, the routing reads the primary.
        let state = SidebarSelectionState()
        state.selectedItemId = "doc:image-1"
        state.selectProject(projectId)
        #expect(state.selectedDestinations == [.library(projectId)])
        #expect(state.selectedDestination == .library(projectId))
        // The project click clears the Library pane's pick (ContentView+StateEvents), so the
        // Inspector routes with an empty browser selection.
        #expect(state.inspectedProjectId(browserSelection: []) == projectId)
    }

    @Test("a pick in the Library pane after the project click is what the Inspector shows")
    func libraryPanePickOutranksTheProject() {
        // WHY: the Inspector follows the newest visible selection; once a row in the pane is
        // picked, showing the project would inspect something the user is not pointing at.
        let state = SidebarSelectionState()
        state.selectProject(projectId)
        #expect(state.inspectedProjectId(browserSelection: ["image-1"]) == nil)
    }

    @Test("a folder click after the project: the Inspector follows the folder")
    func folderAfterProjectInspectsTheFolder() {
        // WHY: the project inspector must not stick; a folder row is a new selection and the
        // folder path (`inspectorDocument`) takes the Inspector back.
        let state = SidebarSelectionState()
        state.selectProject(projectId)
        state.selectedItemId = "doc:folder-1"
        #expect(state.selectedDestinations == [.document("folder-1")])
        #expect(state.inspectedProjectId(browserSelection: []) == nil)
    }

    @Test("a source click still opens Finder-like, never the project inspector")
    func sourceClickUnchanged() {
        // WHY: #5428 just landed the source route; the project route must not capture it.
        let state = SidebarSelectionState()
        state.selectProject(projectId)
        state.selectedItemId = "doc:image-1"
        #expect(state.inspectedProjectId(browserSelection: []) == nil)
        let image = Document(id: "image-1", parentId: "folder-1", docType: .file, fileType: .image, name: "scan.jpg")
        #expect(
            SidebarSourceOpen.plan(for: image, previewShowing: true)
                == SidebarSourceOpen(folderId: "folder-1", selection: ["image-1"], opensPreview: false)
        )
    }
}
