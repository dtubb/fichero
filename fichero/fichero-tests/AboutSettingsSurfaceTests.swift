import XCTest

final class AboutSettingsSurfaceTests: XCTestCase {
    func testSettingsViewHostsAboutTabOnTouchPlatforms() throws {
        let source = try Self.appSource("Views/Settings/SettingsView.swift")
        XCTAssertTrue(source.contains("#if !canImport(AppKit)"))
        XCTAssertTrue(source.contains("AboutView()"))
        XCTAssertTrue(source.contains("Label(\"About\", systemImage: \"info.circle\")"))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
