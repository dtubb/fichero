import XCTest

final class MenuShortcutBoundaryTests: XCTestCase {
    func testViewMenuAvoidsImportAndSearchShortcutCollisions() throws {
        let source = try Self.appSource("Views/Shell/Menu/ViewMenuCommands.swift")
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
