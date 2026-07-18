import XCTest

final class SceneStorageUsageTests: XCTestCase {
    func testMainContentModifiersDoesNotOwnSceneStorage() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentViewModifiers.swift")
        XCTAssertFalse(source.contains("@SceneStorage(\"currentLayoutMode\")"))
        XCTAssertTrue(source.contains("@Binding var currentLayoutMode: LayoutMode"))
    }

    func testContentViewStillOwnsCurrentLayoutSceneStorage() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentView.swift")
        XCTAssertTrue(source.contains("@SceneStorage(\"currentLayoutMode\")"))
        XCTAssertTrue(source.contains("currentLayoutMode: $currentLayoutMode"))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
