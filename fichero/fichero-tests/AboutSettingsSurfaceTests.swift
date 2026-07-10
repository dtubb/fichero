import XCTest

final class AboutSettingsSurfaceTests: XCTestCase {
    func testSettingsViewHostsAboutTabOnTouchPlatforms() throws {
        let source = try Self.appSource("Views/Settings/SettingsView.swift")
        XCTAssertTrue(source.contains("#if !canImport(AppKit)"))
        XCTAssertTrue(source.contains("AboutView()"))
        XCTAssertTrue(source.contains("Label(\"About\", systemImage: \"info.circle\")"))
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
        XCTAssertTrue(source.contains("MCPServersView()"))
        XCTAssertTrue(source.contains("IntegrationsSettingsView(showAutomationRules: featureManager.isAutomationEnabled)"))
        XCTAssertTrue(source.contains("Label(\"MCP\", systemImage: \"server.rack\")"))
        XCTAssertTrue(source.contains("Label(\"Integrations\", systemImage: \"app.connected.to.app.below.fill\")"))
    }

    func testAboutViewUsesBundleCopyrightBeforeFallback() throws {
        let source = try Self.appSource("Views/AboutView.swift")
        XCTAssertTrue(source.contains("NSHumanReadableCopyright"))
        XCTAssertTrue(source.contains("AboutInfo.copyrightLine("))
        XCTAssertTrue(source.contains("fallbackCopyright"))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
