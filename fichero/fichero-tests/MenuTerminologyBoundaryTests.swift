import XCTest

final class MenuTerminologyBoundaryTests: XCTestCase {
    func testFileAndImportMenusUseLibraryAndMoveTerminology() throws {
        let fileMenuSource = try Self.appSource("Views/Menu/FileMenuCommands.swift")
        XCTAssertTrue(fileMenuSource.contains("Button(\"Close Library\")"))
        XCTAssertTrue(fileMenuSource.contains("Button(\"Save Library As...\")"))
        XCTAssertFalse(fileMenuSource.contains("Close Database"))
        XCTAssertFalse(fileMenuSource.contains("Save Database As..."))

        let focusedCommandsSource = try Self.appSource("Views/Menu/FocusedCommandButtons.swift")
        XCTAssertTrue(focusedCommandsSource.contains("Button(\"Move Files...\")"))
        XCTAssertFalse(focusedCommandsSource.contains("Button(\"Add Files...\")"))

        let addItemMenuSource = try Self.appSource("Views/Menu/AddItemMenu.swift")
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
