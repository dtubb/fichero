import XCTest

final class ProgressViewUsageTests: XCTestCase {
    func testIndeterminateProgressViewsDoNotUseFixedFrames() throws {
        let sources = [
            try Self.appSource("Views/Inspector/Document/Info/DocumentInspectorInfoTab+Prototype.swift"),
            try Self.appSource("Views/Library/NodeClassPicker.swift"),
            try Self.appSource("Views/Workflow/NodeConfigs/ExtractEntitiesNodeConfig.swift")
        ]

        for source in sources {
            XCTAssertFalse(source.contains("ProgressView().scaleEffect(0.6).frame("))
            XCTAssertTrue(source.contains("ProgressView().controlSize(.mini)"))
        }
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
