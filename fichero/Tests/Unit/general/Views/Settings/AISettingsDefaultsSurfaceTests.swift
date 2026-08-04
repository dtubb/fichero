import XCTest

final class AISettingsDefaultsSurfaceTests: XCTestCase {
    func testDefaultsTabIncludesMediumAndVisionTierSections() throws {
        let source = try Self.appSource("Views/Settings/AI/AISettingsView+Tabs.swift")
        XCTAssertTrue(source.contains("Default Medium Model ($medium)"))
        XCTAssertTrue(source.contains("Vision Small Model ($vision_small)"))
        XCTAssertTrue(source.contains("Vision Medium Model ($vision_medium)"))
        XCTAssertTrue(source.contains("Vision Large Model ($vision_large)"))
    }

    func testSettingsViewOwnsTierSpecificModelLists() throws {
        let source = try Self.appSource("Views/Settings/AI/AISettingsView.swift")
        XCTAssertTrue(source.contains("@State var mediumModels: [ModelInfo] = []"))
        XCTAssertTrue(source.contains("@State var visionSmallModels: [ModelInfo] = []"))
        XCTAssertTrue(source.contains("@State var visionMediumModels: [ModelInfo] = []"))
        XCTAssertTrue(source.contains("@State var visionLargeModels: [ModelInfo] = []"))
    }

    func testModelManagementTabsStayInsideSettingsAndRespectTierGate() throws {
        let source = try Self.appSource("Views/Settings/AI/AISettingsView.swift")
        XCTAssertTrue(source.contains("featureManager.isSettingsModelsTabEnabled"))
        XCTAssertTrue(source.contains("Text(\"Models & Providers\").tag(AISettingsTab.providers)"))
        XCTAssertTrue(source.contains("Text(\"Downloads\").tag(AISettingsTab.downloads)"))
        // #4503: the "Local LLM" tab is GONE — MLX is a provider row inside
        // Models & Providers. The CASE survives so a persisted selection or a
        // pre-#4503 deep link resolves to the providers tab, never to nothing.
        XCTAssertFalse(source.contains("Text(\"Local LLM\")"))
        XCTAssertTrue(source.contains("case .providers, .localLLM:"))
        XCTAssertTrue(source.contains("switch effectiveSelectedTab"))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = try AppSource.root()
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
