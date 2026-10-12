import Foundation
@testable import Fichero
import Testing

/// #5652 slice 2: the top-level Read menu became Page and the Segment menu folded into it; Project › Read holds a
/// Reading ▸ submenu of the reading verbs on the selection. What breaks without these: a bar that still shows Read
/// or Segment, a page verb lost in the move, or a reading verb in the menu bar that is not the context menus' item.
@MainActor
@Suite("Page and Project › Read › Reading ▸ (#5652 slice 2)")
struct PageMenuTests {
    @Test("the bar has a Page menu and no Read or Segment menu")
    func pageReplacesReadAndSegment() throws {
        let menus = try Self.appSource("App/Menus/PageAndProjectMenuCommands.swift")
        #expect(menus.contains("CommandMenu(\"Page\")"))
        #expect(!menus.contains("CommandMenu(\"Read\")"))
        #expect(!menus.contains("CommandMenu(\"Segment\")"))
        let app = try Self.appSource("FicheroApp.swift")
        #expect(app.contains("PageAndProjectMenuCommands()"))
    }

    @Test("Page holds Reader Lens, the doubtful words, Zoom, Rotate and the page's segments, in that order")
    func pageHoldsThePageVerbs() throws {
        let menus = try Self.appSource("App/Menus/PageAndProjectMenuCommands.swift")
        let page = try #require(menus.range(of: "CommandMenu(\"Page\")"))
        let project = try #require(menus.range(of: "CommandMenu(\"Project\")"))
        let body = String(menus[page.upperBound..<project.lowerBound])
        let order = ["Menu(\"Reader Lens\")", "DoubtfulWordMenuSection()", "ImagePreviewMenuCommands()",
                     "RotateImageMenuSection()", "Section(\"Segments\") {\n                SegmentMenuContent()"]
        let positions = order.map { body.range(of: $0)?.lowerBound }
        #expect(positions.allSatisfy { $0 != nil }, "Page is missing one of \(order)")
        let found = positions.compactMap { $0 }
        #expect(found == found.sorted(), "Page's items are out of order")
    }

    @Test("the segments' items still say why they cannot act")
    func segmentsKeepTheirReasons() throws {
        let segments = try Self.appSource("App/Menus/FocusedCommands/SegmentMenuCommands.swift")
        #expect(segments.contains("Text(\"Show a page in \\(SourcePane.name) to edit its segments\")"))
        #expect(segments.contains("Text(\"Turn on Edit Segments to change segments\")"))
        #expect(segments.contains("Text(\"Select segments on the page\")"))
    }

    @Test("Project › Read › Reading ▸ holds Run the Recipe on This Folder…, the folder context menus' item")
    func readingSubmenu() throws {
        let menus = try Self.appSource("App/Menus/PageAndProjectMenuCommands.swift")
        #expect(menus.contains("case .read:\n            Section(stage.title) {"))
        #expect(menus.contains("Menu(\"Reading\") {\n                    FocusedRunRecipeOnFolderButton()"))
        let recipe = try Self.appSource("App/Menus/FocusedCommands/FocusedCommandButtons+Recipe.swift")
        #expect(recipe.contains("RunRecipeOnFolderMenuItem(folderId: target?.recipeFolderId, library: target?.library)"))
        #expect(recipe.contains("Text(\"Open a project to run its recipe\")"))
        #expect(recipe.contains("Text(RecipeFolderScope.noFolderReason)"))
        #expect(RecipeFolderScope.noFolderReason == "Select one folder to run the recipe on")
        let library = try Self.appSource("Views/Library/LibraryView+ContextMenu.swift")
        #expect(library.contains("RunRecipeOnFolderMenuItem("))
        let sidebar = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift")
        #expect(sidebar.contains("RunRecipeOnFolderMenuItem("))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }
}
