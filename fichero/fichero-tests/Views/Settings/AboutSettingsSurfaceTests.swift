import XCTest

final class AboutSettingsSurfaceTests: XCTestCase {
    func testSettingsViewHostsAboutTabOnTouchPlatforms() throws {
        let source = try Self.appSource("Views/Settings/SettingsView.swift")
        XCTAssertTrue(source.contains("#if !canImport(AppKit)"))
        XCTAssertTrue(source.contains("AboutView()"))
        // The sidebar row helper takes only the tab now; title/icon/tint moved to
        // SettingsSectionInfo (SettingsDetailHeader).
        XCTAssertTrue(source.contains("row(.about)"))
        let headerSource = try Self.appSource("Views/Settings/SettingsDetailHeader.swift")
        XCTAssertTrue(headerSource.contains(#"SettingsSectionInfo(title: "About", symbol: "info.circle", tint: .gray)"#))
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
        // Row helper takes only the tab now; title/icon/tint live in SettingsSectionInfo.
        XCTAssertTrue(source.contains("row(.mcp)"))
        let headerSource = try Self.appSource("Views/Settings/SettingsDetailHeader.swift")
        XCTAssertTrue(headerSource.contains(#"SettingsSectionInfo(title: "MCP", symbol: "server.rack", tint: .green)"#))
        // #4024: the Settings IA reorg dropped the standalone Integrations
        // sidebar row (it returns under Workflows when real) but the tab and
        // its detail pane are still routed here, so assert that instead.
        XCTAssertTrue(source.contains("case .integrations:"))
        XCTAssertTrue(source.contains("MCPServersView()"))
        XCTAssertTrue(source.contains("IntegrationsSettingsView(showAutomationRules: featureManager.isAutomationEnabled)"))
    }

    func testAppStateRoutesLegacyMCPAndIntegrationsTriggersIntoSettings() throws {
        let source = try [
            Self.appSource("App/AppState.swift"),
            Self.appSource("App/AppState+Settings.swift")
        ].joined(separator: "\n")
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
        let baseURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
