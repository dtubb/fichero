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

    func testModelManagementTabsMovedToTheModelsWindowStillRespectTierGateAndSettingsLinksThere() throws {
        let source = try Self.appSource("Views/Settings/AI/AISettingsView.swift")
        XCTAssertTrue(source.contains("featureManager.isSettingsModelsTabEnabled"))
        XCTAssertTrue(source.contains("case .window: modelsTabEnabled ? [.defaults, .providers, .downloads] : [.defaults]"))
        XCTAssertTrue(source.contains("case .settings: [.advanced]"))
        // #4503: the "Local LLM" tab is GONE; the case survives and resolves to the providers tab.
        XCTAssertFalse(source.contains("Text(\"Local LLM\")"))
        XCTAssertTrue(source.contains("case .providers, .localLLM:"))
        XCTAssertTrue(source.contains("switch effectiveSelectedTab"))
        let tabs = try Self.appSource("Views/Settings/AI/AISettingsView+Tabs.swift")
        XCTAssertTrue(tabs.contains("openWindow(id: ModelsWindowModel.windowID)"))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = try AppSource.root()
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
