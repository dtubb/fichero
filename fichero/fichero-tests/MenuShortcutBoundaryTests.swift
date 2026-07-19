import XCTest

final class MenuShortcutBoundaryTests: XCTestCase {
    func testViewMenuAvoidsImportAndSearchShortcutCollisions() throws {
        // #4024: pane-visibility keyboard shortcuts moved to ViewMenuPaneSections.swift.
        let source = try Self.appSource("Views/Shell/Menu/ViewMenuPaneSections.swift")
        XCTAssertTrue(source.contains(".keyboardShortcut(\"i\", modifiers: [.command, .control])"))
        XCTAssertFalse(source.contains(".keyboardShortcut(\"i\", modifiers: [.command, .option])"))
        XCTAssertTrue(source.contains(".keyboardShortcut(\"f\", modifiers: [.command, .option])"))
        XCTAssertFalse(source.contains(".keyboardShortcut(\"f\", modifiers: .command)"))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
