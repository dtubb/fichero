import SwiftUI

// MARK: - A project's verbs, one component each (#5652 slice 4, group 5)

// Rename Project…, Edit Document Types…, Share Project…, Show in Finder and Delete Project… are ONE item each: a
// project's row menu in the sidebar (and the always-there project's empty-area menu) renders them on its project,
// and the menu bar renders them on the key window's project (File for the project itself, Project for its
// document types), through `ProjectVerbsTarget`, which the window's own project row (or the sidebar, for the
// always-there project) publishes. Each acts through that row's one path (its rename prompt, its share
// sheet, its type editor, its delete confirmation), and is disabled with its reason under it.

/// A project as its verbs see it. Equatable on what the menu shows, never on the closures.
struct ProjectVerbsTarget: Equatable {
    let projectId: UUID
    /// What the project's kind allows (`ProjectRowMenuOffers`: the always-there project has no name to change, no
    /// share, no close and no delete).
    let offers: ProjectRowMenuOffers
    /// The signed-in person may change it (owner or editor); a viewer reads only.
    let canWrite: Bool
    var rename: (@MainActor () -> Void)?
    var editDocumentTypes: (@MainActor () -> Void)?
    var share: (@MainActor () -> Void)?
    var showInFinder: (@MainActor () -> Void)?
    var delete: (@MainActor () -> Void)?

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.projectId == rhs.projectId && lhs.offers == rhs.offers && lhs.canWrite == rhs.canWrite
    }
}

extension FocusedValues {
    /// The key window's project, as its row in the sidebar offers it.
    @Entry var projectVerbs: ProjectVerbsTarget?
}

enum ProjectVerbs {
    static let renameTitle = "Rename Project…"
    static let editDocumentTypesTitle = AlwaysThereProjectMenu.editDocumentTypes
    static let shareTitle = "Share Project…"
    static let showInFinderTitle = AlwaysThereProjectMenu.showInFinder
    static let deleteTitle = "Delete Project…"

    static let noProject = "Show a project in this window"
    static let readOnly = "You have view-only access to this project"

    /// Why a project verb cannot act: no project in this window, what the project's kind refuses (`refused`, in
    /// words), or a viewer's access.
    static func reason(_ target: ProjectVerbsTarget?, refused: String?, writes: Bool,
                       action: (ProjectVerbsTarget) -> (@MainActor () -> Void)?) -> String? {
        guard let target else { return noProject }
        if let refused { return refused }
        if writes, !target.canWrite { return readOnly }
        return action(target) == nil ? "Show the project in the sidebar to use this" : nil
    }

    static func renameReason(_ target: ProjectVerbsTarget?) -> String? {
        reason(target, refused: target?.offers.rename == false ? "The always-there project has no name to change" : nil,
               writes: true, action: \.rename)
    }

    static func editDocumentTypesReason(_ target: ProjectVerbsTarget?) -> String? {
        reason(target, refused: nil, writes: true, action: \.editDocumentTypes)
    }

    static func shareReason(_ target: ProjectVerbsTarget?) -> String? {
        let refused: String? = if target?.offers.close == false {
            "The always-there project is not shared"
        } else if target?.offers.share == false {
            "Turn on sharing in Settings to share a project"
        } else {
            nil
        }
        return reason(target, refused: refused, writes: true, action: \.share)
    }

    static func showInFinderReason(_ target: ProjectVerbsTarget?) -> String? {
        reason(target, refused: nil, writes: false, action: \.showInFinder)
    }

    static func deleteReason(_ target: ProjectVerbsTarget?) -> String? {
        reason(target, refused: target?.offers.delete == false ? "The always-there project cannot be deleted" : nil,
               writes: true, action: \.delete)
    }
}

// MARK: - The items

struct RenameProjectMenuItem: View {
    let target: ProjectVerbsTarget?

    var body: some View {
        Button(ProjectVerbs.renameTitle) { target?.rename?() }
            .disabled(ProjectVerbs.renameReason(target) != nil)
    }
}

struct EditDocumentTypesMenuItem: View {
    let target: ProjectVerbsTarget?

    var body: some View {
        Button(ProjectVerbs.editDocumentTypesTitle) { target?.editDocumentTypes?() }
            .disabled(ProjectVerbs.editDocumentTypesReason(target) != nil)
    }
}

struct ShareProjectMenuItem: View {
    let target: ProjectVerbsTarget?

    var body: some View {
        Button(ProjectVerbs.shareTitle) { target?.share?() }
            .disabled(ProjectVerbs.shareReason(target) != nil)
    }
}

struct ShowProjectInFinderMenuItem: View {
    let target: ProjectVerbsTarget?

    var body: some View {
        Button(ProjectVerbs.showInFinderTitle) { target?.showInFinder?() }
            .disabled(ProjectVerbs.showInFinderReason(target) != nil)
    }
}

struct DeleteProjectMenuItem: View {
    let target: ProjectVerbsTarget?

    var body: some View {
        Button(ProjectVerbs.deleteTitle, role: .destructive) { target?.delete?() }
            .disabled(ProjectVerbs.deleteReason(target) != nil)
    }
}

/// Close Project, as ONE item: File (⌃⌘W, the key window's project) and a project row's menu (its project).
struct CloseProjectMenuItem: View {
    let close: (@MainActor () -> Void)?

    static let title = "Close Project"

    var body: some View {
        Button(Self.title) { close?() }
            .disabled(close == nil)
    }
}

// MARK: - The menu bar

/// File's project verbs on the key window's project, each disabled with its reason under it. No chords.
struct FocusedProjectFileButtons: View {
    @FocusedValue(\.projectVerbs) private var target

    var body: some View {
        RenameProjectMenuItem(target: target)
        if let reason = ProjectVerbs.renameReason(target) { Text(reason) }
        ShareProjectMenuItem(target: target)
        if target != nil, let reason = ProjectVerbs.shareReason(target) { Text(reason) }
        ShowProjectInFinderMenuItem(target: target)
        if target != nil, let reason = ProjectVerbs.showInFinderReason(target) { Text(reason) }
        DeleteProjectMenuItem(target: target)
        if target != nil, let reason = ProjectVerbs.deleteReason(target) { Text(reason) }
    }
}

/// Project › Edit Document Types… on the key window's project.
struct FocusedEditDocumentTypesButton: View {
    @FocusedValue(\.projectVerbs) private var target

    var body: some View {
        EditDocumentTypesMenuItem(target: target)
        if let reason = ProjectVerbs.editDocumentTypesReason(target) { Text(reason) }
    }
}
