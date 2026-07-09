import XCTest

final class AISettingsDefaultsSurfaceTests: XCTestCase {
    func testDefaultsTabIncludesMediumAndVisionTierSections() throws {
        let source = try Self.appSource("Views/Settings/AISettingsView+Tabs.swift")
        XCTAssertTrue(source.contains("Default Medium Model ($medium)"))
        XCTAssertTrue(source.contains("Vision Small Model ($vision_small)"))
        XCTAssertTrue(source.contains("Vision Medium Model ($vision_medium)"))
        XCTAssertTrue(source.contains("Vision Large Model ($vision_large)"))
    }

    func testSettingsViewOwnsTierSpecificModelLists() throws {
        let source = try Self.appSource("Views/Settings/AISettingsView.swift")
        XCTAssertTrue(source.contains("@State var mediumModels: [ModelInfo] = []"))
        XCTAssertTrue(source.contains("@State var visionSmallModels: [ModelInfo] = []"))
        XCTAssertTrue(source.contains("@State var visionMediumModels: [ModelInfo] = []"))
        XCTAssertTrue(source.contains("@State var visionLargeModels: [ModelInfo] = []"))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
