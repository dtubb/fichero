import XCTest

final class AboutSettingsSurfaceTests: XCTestCase {
    func testSettingsViewHostsAboutTabOnTouchPlatforms() throws {
        let source = try Self.appSource("Views/Settings/SettingsView.swift")
        XCTAssertTrue(source.contains("#if !canImport(AppKit)"))
        XCTAssertTrue(source.contains("AboutView()"))
        XCTAssertTrue(source.contains("row(.about, \"About\", \"info.circle\")"))
    }

    func testAppMenuDoesNotDuplicateAISettingsEntry() throws {
        let source = try Self.appSource("FicheroApp.swift")
        XCTAssertFalse(source.contains("AI Providers & Models..."))
        XCTAssertFalse(source.contains("showSettingsWindow:"))
        XCTAssertFalse(source.contains("MCP Servers..."))
        XCTAssertFalse(source.contains("Button(\"Folder Watchers...\")"))
        XCTAssertFalse(source.contains("Button(\"App Observers...\")"))
        XCTAssertFalse(source.contains("Automation Rules..."))
    }

    func testSettingsViewHostsMCPAndIntegrationsTabs() throws {
        let source = try Self.appSource("Views/Settings/SettingsView.swift")
        XCTAssertTrue(source.contains("NavigationSplitView"))
        XCTAssertTrue(source.contains("row(.mcp, \"MCP\", \"server.rack\")"))
        XCTAssertTrue(source.contains("row(.integrations, \"Integrations\", \"app.connected.to.app.below.fill\")"))
        XCTAssertTrue(source.contains("MCPServersView()"))
        XCTAssertTrue(source.contains("IntegrationsSettingsView(showAutomationRules: featureManager.isAutomationEnabled)"))
    }

    func testAppStateRoutesLegacyMCPAndIntegrationsTriggersIntoSettings() throws {
        let source = try Self.appSource("App/AppState.swift")
        XCTAssertTrue(source.contains("var selectedSettingsTab: SettingsTab = .aiModels"))
        XCTAssertTrue(source.contains("openSettings(tab: .mcp)"))
        XCTAssertEqual(source.components(separatedBy: "openSettings(tab: .integrations)").count - 1, 3)
        XCTAssertTrue(source.contains("case .mcp where !featureManager.isMCPEnabled:"))
        XCTAssertTrue(source.contains("case .integrations where !featureManager.isIntegrationsEnabled:"))
        XCTAssertEqual(source.components(separatedBy: "return .aiModels").count - 1, 2)
        XCTAssertTrue(source.contains("NSApp.sendAction(Selector((\"showSettingsWindow:\")), to: nil, from: nil)"))
    }

    func testShellNoLongerPresentsSeparateMCPOrIntegrationsSheets() throws {
        let libraryWindowSource = try Self.appSource("App/LibraryWindow.swift")
        let modifiersSource = try Self.appSource("Views/Shell/ContentView/ContentViewModifiers.swift")
        XCTAssertFalse(libraryWindowSource.contains("MCPServersSheet()"))
        XCTAssertFalse(libraryWindowSource.contains("IntegrationsPlaceholderSheet("))
        XCTAssertFalse(modifiersSource.contains("MCPServersSheet()"))
    }

    func testAboutViewUsesBundleCopyrightBeforeFallback() throws {
        let source = try Self.appSource("Views/About/AboutView.swift")
        XCTAssertTrue(source.contains("NSHumanReadableCopyright"))
        XCTAssertTrue(source.contains("AboutInfo.copyrightLine("))
        XCTAssertTrue(source.contains("fallbackCopyright"))
    }

    func testMacAboutWindowInjectsAppState() throws {
        let source = try Self.appSource("FicheroApp.swift")
        let aboutWindow = try XCTUnwrap(
            source.components(separatedBy: "Window(\"About Fichero\", id: \"about\") {").dropFirst().first
        )
        XCTAssertTrue(aboutWindow.contains("AboutView()\n                .environment(appState)"))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
