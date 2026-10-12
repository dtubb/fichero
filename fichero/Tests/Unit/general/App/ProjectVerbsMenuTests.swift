import Foundation
@testable import Fichero
import Testing

/// #5652 slice 4, group 5: a project's verbs (Rename Project…, Edit Document Types…, Share Project…, Show in Finder,
/// Delete Project…, Close Project) are one item each, which a project's row menu and the always-there project's
/// empty-area menu render on their project, and File and Project render on the key window's project. Activity's
/// Delete is Edit › Delete's item. What breaks without these: the always-there project offered a rename or a delete,
/// a viewer offered a change, an item on with no project (or off with no word), or a press reaching another path.
@MainActor
@Suite("A project's verbs, one component each (#5652 slice 4)")
struct ProjectVerbsMenuTests {
    private func project(alwaysThere: Bool = false, multiuser: Bool = true, canWrite: Bool = true,
                         calls: @escaping (String) -> Void = { _ in }) -> ProjectVerbsTarget {
        var target = ProjectVerbsTarget(
            projectId: UUID(), offers: .forProject(isAlwaysThere: alwaysThere, multiuser: multiuser), canWrite: canWrite
        )
        if target.offers.rename { target.rename = { calls("rename") } }
        target.editDocumentTypes = { calls("types") }
        if target.offers.share { target.share = { calls("share") } }
        target.showInFinder = { calls("finder") }
        if target.offers.delete { target.delete = { calls("delete") } }
        return target
    }

    @Test("a project a person set up: every verb acts")
    func namedProject() {
        let named = project()
        #expect(ProjectVerbs.renameReason(named) == nil)
        #expect(ProjectVerbs.editDocumentTypesReason(named) == nil)
        #expect(ProjectVerbs.shareReason(named) == nil)
        #expect(ProjectVerbs.showInFinderReason(named) == nil)
        #expect(ProjectVerbs.deleteReason(named) == nil)
    }

    @Test("the always-there project keeps its document types and Show in Finder, and says why it has no others")
    func alwaysThereProject() {
        let always = project(alwaysThere: true)
        #expect(ProjectVerbs.renameReason(always) == "The always-there project has no name to change")
        #expect(ProjectVerbs.shareReason(always) == "The always-there project is not shared")
        #expect(ProjectVerbs.deleteReason(always) == "The always-there project cannot be deleted")
        #expect(ProjectVerbs.editDocumentTypesReason(always) == nil)
        #expect(ProjectVerbs.showInFinderReason(always) == nil)
    }

    @Test("a viewer reads only; sharing off says where to turn it on; no project says to show one")
    func viewerSharingAndNone() {
        let viewer = project(canWrite: false)
        #expect(ProjectVerbs.renameReason(viewer) == ProjectVerbs.readOnly)
        #expect(ProjectVerbs.deleteReason(viewer) == ProjectVerbs.readOnly)
        #expect(ProjectVerbs.showInFinderReason(viewer) == nil, "seeing where it is changes nothing")
        #expect(ProjectVerbs.shareReason(project(multiuser: false)) == "Turn on sharing in Settings to share a project")
        #expect(ProjectVerbs.renameReason(nil) == ProjectVerbs.noProject)
    }

    @Test("each press reaches the project row's own path")
    func pressesReachTheRow() {
        var calls: [String] = []
        let named = project { calls.append($0) }
        named.rename?()
        named.editDocumentTypes?()
        named.share?()
        named.showInFinder?()
        named.delete?()
        #expect(calls == ["rename", "types", "share", "finder", "delete"])
    }

    @Test("the project verbs and the always-there project's menu say the same words")
    func oneSpelling() {
        #expect(ProjectVerbs.editDocumentTypesTitle == AlwaysThereProjectMenu.editDocumentTypes)
        #expect(ProjectVerbs.showInFinderTitle == AlwaysThereProjectMenu.showInFinder)
        #expect(CloseProjectMenuItem.title == "Close Project")
        for title in [ProjectVerbs.renameTitle, ProjectVerbs.shareTitle, ProjectVerbs.deleteTitle] {
            #expect(title.hasSuffix("…") && !title.contains("..."), "\(title)")
        }
    }

    @Test("the target compares by the project and what it allows, so the same project does not republish")
    func equality() {
        let id = UUID()
        let lhs = ProjectVerbsTarget(projectId: id, offers: .forProject(isAlwaysThere: false, multiuser: true), canWrite: true)
        var rhs = lhs
        rhs.rename = {}
        #expect(lhs == rhs)
        #expect(lhs != ProjectVerbsTarget(projectId: id, offers: lhs.offers, canWrite: false))
    }
}
