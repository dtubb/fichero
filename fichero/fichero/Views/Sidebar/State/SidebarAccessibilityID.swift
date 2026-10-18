import Foundation

/// The sidebar's stable accessibility identifiers (`sidebar.accessibility-identifiers`, #5763): one declaration, so the
/// views and the UI tests spell them the same way. Every row, project header, the Projects heading and the list has one.
nonisolated enum SidebarAccessibilityID {
    static let list = "sidebar.list"
    static let projectsHeading = "sidebar.projectsHeading"

    static func row(_ itemId: String) -> String { "sidebar.row.\(itemId)" }
    static func project(_ libraryId: UUID) -> String { "sidebar.project.\(libraryId.uuidString)" }
    static func trash(_ libraryId: UUID) -> String { "sidebar.trash.\(libraryId.uuidString)" }
    static func models(_ libraryId: UUID) -> String { "sidebar.models.\(libraryId.uuidString)" }
}
