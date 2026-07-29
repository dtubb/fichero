import XCTest

final class SceneStorageUsageTests: XCTestCase {
    func testMainContentModifiersDoesNotOwnSceneStorage() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentViewModifiers.swift")
        XCTAssertFalse(source.contains("@SceneStorage(\"currentLayoutMode\")"))
        XCTAssertTrue(source.contains("@Binding var currentLayoutMode: LayoutMode"))
    }

    func testContentViewStillOwnsCurrentLayoutSceneStorage() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentView.swift")
        // ContentView still DECLARES the scene storage — that ownership is the
        // point of this test. The binding is passed down from the root layout,
        // where 408e4ae81 moved the view-builders.
        let rootLayout = try Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift")
        XCTAssertTrue(source.contains("@SceneStorage(\"currentLayoutMode\")"))
        XCTAssertFalse(rootLayout.contains("@SceneStorage(\"currentLayoutMode\")"))
        XCTAssertTrue(rootLayout.contains("currentLayoutMode: $currentLayoutMode"))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
