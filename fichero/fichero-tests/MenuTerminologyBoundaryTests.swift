import XCTest

final class MenuTerminologyBoundaryTests: XCTestCase {
    func testFileAndImportMenusUseLibraryAndMoveTerminology() throws {
        let fileMenuSource = try Self.appSource("App/Menus/FileMenuCommands.swift")
        XCTAssertTrue(fileMenuSource.contains("Button(\"Close Library\")"))
        XCTAssertTrue(fileMenuSource.contains("Button(\"Save Library As...\")"))
        XCTAssertTrue(fileMenuSource.contains("Label(\"Markdown Static Site...\", systemImage: \"globe\")"))
        XCTAssertTrue(fileMenuSource.contains("library.documentService.exportEleventySite("))
        XCTAssertTrue(fileMenuSource.contains("Text(\"Couldn’t load recent libraries\")"))
        XCTAssertTrue(fileMenuSource.contains(".disabled(registry.libraries.isEmpty && registry.fetchError == nil)"))
        XCTAssertFalse(fileMenuSource.contains("Close Database"))
        XCTAssertFalse(fileMenuSource.contains("Save Database As..."))
        XCTAssertFalse(fileMenuSource.contains("Label(\"Static Site (11ty)...\", systemImage: \"globe\")"))

        let focusedCommandsSource = try Self.appSource("App/Menus/FocusedCommandButtons.swift")
            + Self.appSource("App/Menus/FocusedCommandButtons+SidebarActions.swift")
        XCTAssertTrue(focusedCommandsSource.contains("Button(\"Move Files...\")"))
        XCTAssertFalse(focusedCommandsSource.contains("Button(\"Add Files...\")"))

        let addItemMenuSource = try Self.appSource("App/Menus/AddItemMenu.swift")
        XCTAssertTrue(addItemMenuSource.contains("Button(\"Move Files...\")"))
        XCTAssertFalse(addItemMenuSource.contains("Button(\"Add Files...\")"))
    }

    func testRenameShortcutIsDeclaredOnlyOnTheFocusedButton() throws {
        let appSource = try Self.appSource("FicheroApp.swift")
        XCTAssertTrue(appSource.contains("FocusedRenameButton()"))
        XCTAssertFalse(appSource.contains("FocusedRenameButton()\n                    .keyboardShortcut(.return, modifiers: [])"))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
