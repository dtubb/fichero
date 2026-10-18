@testable import Fichero
import Foundation
import Testing

/// `sidebar.accessibility-identifiers` (#5763): the identifiers are spelled once, and each view applies its own.
@MainActor
struct SidebarAccessibilityIDTests {
    @Test("the identifier strings")
    func strings() {
        let id = UUID(uuidString: "11111111-2222-3333-4444-555555555555")!
        #expect(SidebarAccessibilityID.list == "sidebar.list")
        #expect(SidebarAccessibilityID.projectsHeading == "sidebar.projectsHeading")
        #expect(SidebarAccessibilityID.row("doc-1") == "sidebar.row.doc-1")
        #expect(SidebarAccessibilityID.project(id) == "sidebar.project.11111111-2222-3333-4444-555555555555")
        #expect(SidebarAccessibilityID.trash(id) == "sidebar.trash.11111111-2222-3333-4444-555555555555")
        #expect(SidebarAccessibilityID.models(id) == "sidebar.models.11111111-2222-3333-4444-555555555555")
    }

    @Test("each view applies its identifier")
    func applied() throws {
        let applied: [(String, String)] = [
            ("Views/Sidebar/Sections/SidebarView+ViewComponents.swift", "SidebarAccessibilityID.list"),
            ("Views/Sidebar/Sections/SidebarView+ViewComponents.swift", "SidebarAccessibilityID.projectsHeading"),
            ("Views/Sidebar/Sections/SidebarTrashRow.swift", "SidebarAccessibilityID.trash(libraryId)"),
            ("Views/Sidebar/Sections/SidebarModelsNode.swift", "SidebarAccessibilityID.models(libraryId)"),
            ("Views/Sidebar/Sections/LibraryHeaderRow.swift", "SidebarAccessibilityID.project(library.id)"),
            ("Views/Sidebar/ItemRow/SidebarItemRow+Presentation+Body.swift", "SidebarAccessibilityID.row(item.id)")
        ]
        for (file, call) in applied {
            let source = try AppSource.code(file)
            #expect(source.contains(".accessibilityIdentifier(\(call))"), "\(file) applies \(call)")
        }
    }
}
