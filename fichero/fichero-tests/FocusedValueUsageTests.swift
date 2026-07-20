import XCTest

final class FocusedValueUsageTests: XCTestCase {
    func testLibrarySortAscendingUsesEquatableFocusedWrapper() throws {
        let shortcutsSource = try Self.appSource("Views/Library/LibraryView+KeyboardShortcuts.swift")
        // #4024: sortAscending focused-value wiring moved to ViewMenuLayoutSections.swift.
        let commandsSource = try Self.appSource("App/Menus/ViewMenuLayoutSections.swift")

        XCTAssertTrue(shortcutsSource.contains("struct FocusedSortAscending: Equatable"))
        XCTAssertTrue(shortcutsSource.contains("typealias Value = FocusedSortAscending"))
        XCTAssertTrue(
            shortcutsSource.contains(
                ".focusedSceneValue(\n                \\.librarySortAscending,\n                FocusedSortAscending("
            )
        )
        XCTAssertTrue(commandsSource.contains("sortAscending?.set(true)"))
        XCTAssertTrue(commandsSource.contains("sortAscending?.value == true"))
        XCTAssertFalse(shortcutsSource.contains(".focusedSceneValue(\\.librarySortAscending, $libraryToolbar.sortAscending)"))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
